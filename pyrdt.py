import argparse
import struct
import math
import csv

def bcd_decode(barray):
    # Little Endian decoder
    basepow = 0
    cumsum = 0
    for octet in barray:
        # Low nybble to high nybble
        cumsum += (octet & 0b00001111) * (10**basepow)
        basepow += 1
        cumsum += ((octet & 0b11110000) >> 4 ) * (10**basepow)
        basepow += 1
    return cumsum

def bcd_encode(dec_value, num_octets):
    """BCD encode (little endian) an integer"""
    # Check that we have sufficent encoding space
    if math.log10(dec_value) >= (num_octets * 2):
        return ValueError("{} cannot be BCD encoded in {} octets".format(dec_value, num_octets))
    encoded = bytearray()
    for i in range(num_octets):
        low_nybble = dec_value % 10
        dec_value = int( dec_value / 10)
        high_nybble = dec_value % 10
        dec_value = int( dec_value / 10 )
        octet = (high_nybble * 16) + low_nybble
        encoded.append(octet)
    return encoded

class Field():
    def __init__(self, **kwargs):

        if 'id' not in kwargs.keys(): raise KeyError("Field __init__ without id: {}".format(kwargs))
        for k,v in kwargs.items():
            setattr(self, k, v)

        self.constraints = []

        self.loaded = False     # change to true when data loaded

    def __str__(self):
        if not self.loaded:
            return "<UNINITIALIZED>"
        if self.type == "ascii":
            return self.value.decode('ascii')
        if self.type == "unicode" or self.type == "utf16":
            return self.value.decode('utf-16').rstrip('\x00')
        elif self.type == "int":
            try:    # transform
                pass
            except AttributeError:
                pass
            return self.value
        elif self.type == "bcd":    # Little Endian
            return bcd_decode(self.value)
        elif self.type == "rev_bcd":    # Big Endian
            return bcd_decode( reversed(self.value) )
        elif self.type == "bcdt":
            # Same as BCD but 2-msb of second octet encode squelch type
            value_copy = bytearray(self.value)
            value_copy[1] &= 0b00111111     # Zero out the squelch coding bits
            tone = bcd_decode(value_copy)

            # Examine the squelch coding bits
            squelch_type_id = ( self.value[1] & 0b11000000 ) >> 6
            if squelch_type_id == 0:
                return "CTCSS {}".format(tone / 10.0)
            elif squelch_type_id==1:
                return "DCS D{}N".format(tone)
            elif squelch_type_id==2:
                return "DCS D{}I".format(tone)
            

    def add_constraint(self):
        pass
    
    def add_transformation(self, direction, funcstr):
        if "lambda" not in funcstr:
            funcstr = "lambda self,x: " + funcstr
        if direction not in ['in', 'out']: raise ValueError("add_transformation() direction not 'in' or 'out'")
        if direction == "in":
            funcstr = "self.transform_in = " + funcstr
            exec(funcstr)
        elif direction == "out":
            funcstr = "self.transform_out = " + funcstr
            exec(funcstr)

    def add_lut(self, lut):
        """Add look-up table (LUT)"""
        self.lut = lut

    def validate(self):
        if self.type == "int":
            try:
                if self.value > self.max_value:
                    raise ValueError("{} : {} greater than defined maximum {}".format(self.id, self.value, self.max_value))
            except AttributeError:
                pass # no max defined
            try:
                if self.value < self.min_value:
                    raise ValueError("{} : {} less than defined minimum {}".format(self.id, self.value, self.min_value))
            except AttributeError:
                pass # no min defined
            try:
                if self.value not in self.allowed_values:
                    raise ValueError("{} : {} not in permitted values list".format(self.id, self.value))
            except AttributeError:
                pass # no allowed_values defined
            
            # Constraints is defined as an empty list at class instantiation
            for c in constraints:
                # check value against constraint by execing the pythonc ode
                # TODO
                pass
            
            return True


# http://www.iz2uuf.net/wp/index.php/2016/06/04/tytera-dm380-codeplug-binary-format/
class Channel():
    first_record_offset = 127013
    record_length = 64
    end_record_offset = first_record_offset + record_length

    channel_struct = struct.Struct("<c c c c c x h c B c B B x c x 4s 4s 2s 2s c c x x 32s")

# http://www.iz2uuf.net/wp/index.php/2016/06/04/tytera-dm380-codeplug-binary-format/
class GeneralSettings():
    first_record_offset = 8805
    record_length = 136 # 144
    end_record_offset = first_record_offset + record_length

    # NB the 'x I' following 'B B B'. This is radio_id, which is 24-bits
    # radio_id is actually a 24-bit unsigned int (max 2^24 ~ 16,776,415 [actually 801 higher?])
    # but since we are storing in little endian byte order and the following byte
    # is unused, we can unpack as I (unsigned 32-bit integer)
    # The alternative would have been '...B I x' but that leftshifts radio id by 8 bits!
    # or to unpack 3 bytes by hand and constrct the 24-bit int by multiplication...
    # Luckily the following octet is zero. e.g. 0xFF 0xFF 0xFF 0x00 = 2^24
    # Will have to be cautious though as the final octet is not guaranteed(?) to be zero
    general_settings_struct = struct.Struct("<20s 20s 24x B B B x I B B B B 2x B B B B x \
                                            B B B B B \
                                            4s 4s \
                                            8s \
                                            32s")
    field_names = ("info1", "info2", \
        "bitfield1", "bitfield2", "bitfield3", \
        "radio_id", "tx_preamble", "group_call_hangtime", "private_call_hangtime", \
        "vox_sensitivity", "rx_lowbat_interval", "call_alert_tone", \
        "lone_worker_resp_time", "lone_worker_reminder_time", \
        "scan_digital_hangtime", "scan_analog_hangtime", \
        "unknown1", "keypad_lock_time", "mode", \
        "poweron_password", "radio_programming_password", \
        "pc_programming_password", \
        "radio_name")

    def __init__(self, file_contents):
        print("class init")

        self.field_dict = {}
        self.field_struct = "< "
        self.field_names2 = []
        offset = 0
        with open("fields_settings.csv", 'r') as fi:
            reader = csv.DictReader(fi)
            for row in reader:
                print(row)
                print(offset)
                row['offset'] = int( row['offset'] )
                row['bits'] = int( row['bits'] )
                while row['offset'] > offset:
                    print(row['offset'], offset)
                    if ((row['offset'] - offset) % 8) == 0:
                        self.field_struct += "{:d}x ".format( (row['offset'] - offset) // 8 )
                        offset += row['bits']
                    elif (row['offset'] - offset) < 8:
                        # arrived at the bitfield. Because first bit in bf not bit 0 of bf,
                        # go ahead and insert marker
                        self.field_struct += "B "
                        self.field_names2.append("bitfield")
                        offset += row['bits']
                    else:
                        padding_bytes = math.floor( (row['offset'] - offset) / 8 )
                        self.field_struct += "{:d}x ".format( padding_bytes )
                        offset += padding_bytes * 8
                # TODO insert padding relative to bitfield top-up, if applicable
                self.field_dict[ row['id'] ] = Field(**row)
                if row['type'] == "utf16" or row['type'] == "ascii" :
                    self.field_struct += "{:d}s ".format( int(row['bits']) // 8 )
                    self.field_names2.append(row['id'])
                else:
                    if row['bits'] < 8: # we are dealing with bitfield
                        # marker should already have been inserted
                self.field_struct += "B "
                self.field_names2.append(row['id'])
                #print("Incrementing offset ({}) by row[bits] ({})".format(offset, row['bits']))
                offset += row['bits']

        field_values = self.general_settings_struct.unpack(file_contents[self.first_record_offset:self.end_record_offset])
        fields = dict(zip(self.field_names, field_values))

        # Info strings are 10 UTF-16 code units (20 bytes)
        fields['info1'] = fields['info1'].decode('utf-16').rstrip('\x00')
        fields['info2'] = fields['info2'].decode('utf-16').rstrip('\x00')

        # bitfield1
        fields['monitor_type']      = (fields['bitfield1'] & 0b00001000) >> 3   # 515
        if fields['monitor_type'] == 0: fields['monitor_type'] = "silent"
        elif fields['monitor_type'] == 1: fields['monitor_type'] = "open"
        else: raise ValueError("Unknown monitor_type") 
        fields['diable_all_leds']   = bool((fields['bitfield1'] & 0b00100000) >> 5)   # 517
        del fields['bitfield1']

        # bitfield2
        fields['talk_permit_tone'] = (fields['bitfield2'] & 0b00000011) # 520
        if fields['talk_permit_tone'] == 0:     fields['talk_permit_tone'] = "none"
        elif fields['talk_permit_tone'] == 1:   fields['talk_permit_tone'] = "digital"
        elif fields['talk_permit_tone'] == 2:   fields['talk_permit_tone'] = "analog"
        elif fields['talk_permit_tone'] == 3:   fields['talk_permit_tone'] = "both"
        else: raise ValueError("Unknown talk_permit_tone")
        fields['password_and_lock_enable'] = bool((fields['bitfield2'] & 0b00000100) >> 2)  # 522
        fields['chfree_indication_tone'] = bool((fields['bitfield2'] & 0b00001000) >> 3)    # 523
        fields['disable_all_tone']  = bool((fields['bitfield2'] & 0b00100000) >> 5)         # 525
        fields['save_mode_receive'] = bool((fields['bitfield2'] & 0b01000000) >> 6)         # 526
        fields['save_preamble']     = bool((fields['bitfield2'] & 0b10000000) >> 7)         # 527 
        del fields['bitfield2']

        # bitfield3 has only a single member
        fields['intro_screen'] = (fields['bitfield3'] & 0b00001000) >> 3    # 531
        if fields['intro_screen'] == 0: fields['intro_screen'] = "string"
        elif fields['intro_screen'] == 1: fields['intro_screen'] = "picture"
        else: raise ValueError("Unknown value for intro_screen")
        del fields['bitfield3']

        if fields['radio_id'] >= 2**24: raise ValueError("radio_id too high")

        # TxPreamble (msec) = 60 * N where 0<=N<=140 according to web
        if fields['tx_preamble'] > 144: raise ValueError("tx_preamble > 144")
        fields['tx_preamble'] *= 60

        # HangTime (msec) = N*100, N<= 70, web says N "must be multiple of 5"
        if fields['group_call_hangtime'] > 70: raise ValueError("group_call_hangtime > 70")
        elif fields['group_call_hangtime'] % 5 != 0: raise ValueError("group_call_hangtime not multiple of 5")
        else: fields['group_call_hangtime'] *= 100

        if fields['private_call_hangtime'] > 70: raise ValueError("private_call_hangtime > 70")
        elif fields['private_call_hangtime'] % 5 != 0: raise ValueError("private_call_hangtime not multiple of 5")
        else: fields['private_call_hangtime'] *= 100

        # VoxSensitivity @ 600
        # Two unknown bytes
        # RxLowBatteryInterval @ 624
        # RX Lowbattery interval: time in sec, s=N*5, N<= 127 (again, according to web)
        if fields['rx_lowbat_interval'] > 127: raise ValueError("rx_lowbat_interval > 127")
        fields['rx_lowbat_interval'] *= 5

        # CallAlertTone; 0=Continue, otherwise time in seconds, s=N*5, N<=240
        if fields['call_alert_tone'] > 240: raise ValueError("call_alert_tone > 240")
        fields['call_alert_tone'] *= 5

        # LoneWorkerRespTime        640
        # LoneWorkerReminderTime    648

        # Unknown octet @ 656

        # ScanDigitalHangTime in ms, ms=N*5, 5<=N<=100; default N=10    (@ 664)
        if fields['scan_digital_hangtime'] < 5 or fields['scan_digital_hangtime'] > 100:
            raise ValueError("scan_digital_hangtime OOR")
        else: fields['scan_digital_hangtime'] *= 5

        if fields['scan_analog_hangtime'] < 5 or fields['scan_analog_hangtime']  > 100:
            raise ValueError("scan_analog_hangtime OOR")
        else: fields['scan_analog_hangtime'] *= 5

        # Unknown1 octet @ 680

        # Mode, 0=MR, 255=CH    (@696)
        if fields['mode'] == 0: fields['mode'] = "MR"
        elif fields['mode'] == 255: fields['mode'] = "CH"
        else: raise ValueError("Unknown value for mode")



        print(fields)

    def field_byid(self, id):
        # TODO find field member and return
        pass

    def write(self, file_contents):
        pass # return file_contents
    
    def _get_info(self, field):
        return fields[field]
    
    def _set_info(self, field, value):
        if len(value) > 20:
            print("WARNING: string {} truncated to 20 characters => {}", value, value[:20])
        fields[field] = value

    def _get_info1(self):
        #return fields[info1].decode('utf-16')
        return _get_info(self, "info1")

    def _set_info1(self, value):
        _set_info(self, "info1", value)
        
    def _get_info2(self):
        #return fields[info1].decode('utf-16')
        return _get_info(self, "info2")

    def _set_info2(self, value):
        _set_info(self, "info2", value)
    
    info_line1 = property(_get_info1, _set_info1)
    info_line2 = property(_get_info2, _set_info2)

with open("md380_james.rdt", "rb") as fi:
    file_contents = fi.read()

gs = GeneralSettings(file_contents)
