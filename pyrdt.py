# http://www.iz2uuf.net/wp/index.php/2016/06/04/tytera-dm380-codeplug-binary-format/

import argparse
import struct
import math
import csv
import copy
import pdb
import pprint
from collections.abc import MutableMapping

DEBUG = False

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

    def __repr__(self):
        if self.type == "bitfield":
            return "<bitfield>"
        if not self.loaded:
            return "<UNINITIALIZED>"
        if self.zero_valued():
            return "Unset/Disabled"
        
        if self.type == "ascii":
            return self._value.decode('ascii')
        elif self.type == "unicode" or self.type == "utf16":
            return self._value.decode('utf-16').rstrip('\x00')
        elif self.type == "int" or self.type == "binary":
            try:    # transform
                pass
            except AttributeError:
                pass
            if type( self._value) is int:
                return str( self._value)
            elif type( self._value) is bytes:
                return str( int.from_bytes(self._value, "little") )
            else:
                return "**UNANTICIPATED int/binary SITUATION**"
        elif self.type == "bcd":    # Little Endian
            return str( bcd_decode(self._value) )
        elif self.type == "rev_bcd":    # Big Endian
            return str( bcd_decode( reversed(self._value) ) )
        elif self.type == "bcdt":
            # Same as BCD but 2-msb of second octet encode squelch type
            value_copy = bytearray(self._value)
            value_copy[1] &= 0b00111111     # Zero out the squelch coding bits
            tone = bcd_decode(value_copy)

            # Examine the squelch coding bits
            squelch_type_id = ( self._value[1] & 0b11000000 ) >> 6
            if DEBUG: print("squelch_type_id=", squelch_type_id)
            if squelch_type_id == 0:
                return "CTCSS {}".format(tone / 10.0)
            elif squelch_type_id==1:
                return "DCS D{}N".format(tone)
            elif squelch_type_id==2:
                return "DCS D{}I".format(tone)
            else:
                return "BCDT unknown: squelch_type_id={}, tone={}, raw={}".format(squelch_type_id, tone, value_copy)
        else:
            return "<unhandled __repr__>"

        return "<<end of __repr__>>"
    
    @property
    def value(self):
        return self._value # TODO return __repr__ ?
    
    @value.setter
    def value(self, value):
        self._value = value
        self.loaded = True
    
    def zero_valued(self):
        possibly_zeroed = False
        if self.bits == 8:
            return (self._value is self.zero_value)
        elif self.bits >= 16:
            for octet in self._value:
                if octet == self.zero_value: possibly_zeroed = True
                else: return False
            return possibly_zeroed
        else:
            return False
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
                if self._value > self.max_value:
                    raise ValueError("{} : {} greater than defined maximum {}".format(self.id, self._value, self.max_value))
            except AttributeError:
                pass # no max defined
            try:
                if self._value < self.min_value:
                    raise ValueError("{} : {} less than defined minimum {}".format(self.id, self._value, self.min_value))
            except AttributeError:
                pass # no min defined
            try:
                if self._value not in self.allowed_values:
                    raise ValueError("{} : {} not in permitted values list".format(self.id, self._value))
            except AttributeError:
                pass # no allowed_values defined
            
            # Constraints is defined as an empty list at class instantiation
            for c in self.constraints:
                # check value against constraint by execing the pythonc ode
                # TODO
                pass
            
            return True
    
class Row(MutableMapping):
    """Class Row encapsulates a set of fields, indexable by id,
    Providing additional metadata including display order, deletion marker
    
    by subclassing, [deleted] can still be accessed/set as a key, but won't
    show up in iteration.
    """

    def __init__(self, fields: dict, ordered_field_list: list = []):
        self._deleted = True                # Change to False once loaded 'n checked
        self._storage = copy.deepcopy(fields)

        if ordered_field_list:
            self._ordered_field_list = ordered_field_list
        else:
            self._ordered_field_list = list( self._storage.keys() )
    def __getitem__(self, key):
        if key == "deleted":
            return self._deleted
        else:
            return self._storage[key]
    def __setitem__(self, key, value):
        if key == "deleted":
            self._deleted = value
        else:
            self._storage[key] = value
    def __delitem__(self, key):
        # Forgetting to delete from the _ordered_field_list leads to subtle error
        self._ordered_field_list.pop( self._ordered_field_list.index(key) )
        del self._storage[key]
    def __iter__(self):
        # overloadd to iterate in specific order
        #return iter(self._storage)
        self._iter_list = copy.copy(self._ordered_field_list)
        return self
    def __next__(self):
        if len(self._iter_list) > 0:
            key = self._iter_list.pop(0)    # pop the head of the list
            return key
        raise StopIteration
    def __len__(self):
        return len(self._storage)

class Table():
    num_records = 1         # Must override except for general_settings
    zero_value  = 0xFF      # Overrride if diff
    
    def _read_fields(self, fn):
        fields = {}
        field_struct = "< "
        field_names  = []

        bitoffset = 0

        bitfield_num = 0    # occasional
        bfname = "ERROR"
        active_bitfield = False

        with open(fn, 'r') as fi:
            reader = csv.DictReader(fi)
            for row in reader:
                # Transform int fields to ints
                row['offset'] = int( row['offset'] )
                row['bits']   = int( row['bits'] )

                # Diagnostics
                if DEBUG:
                    print( "bitoffset : {}".format(bitoffset))
                    print( "row_offset: {}".format(row['offset']))
                    print( "row_bits  : {}".format(row['bits']))
                    print()

                while row['offset'] > bitoffset:
                    # Insert octet-aligned padding, if possible
                    diff = row['offset'] - bitoffset
                    if diff >= 8:
                        # End bitfield, in case we were in one
                        active_bitfield = False
                        bfname = "ERROR"
                        # Now pad up to nearest octet
                        padding_bytes = math.floor( diff / 8)
                        field_struct += "{}x ".format(padding_bytes)
                        #bitoffset += row['bits']
                        #bitoffset += (padding_bytes * 8)    # offset only up to nearest octet
                        bitoffset = row['offset']
                    else:
                        if row['bits'] >= 8: raise ValueError("Apparently a full byte(s) but we ae not octet aligned")
                        # We have a bit (or two) in a bitfield, but it is not octet aligned
                        # Use this chance to insert a bitfield
                        # TODO: but how do we detect start of a bitfield that is octet aligned?
                        if active_bitfield and ( row['offset'] % 8 > 0):
                            # We are currently in a bitfield
                            # No need to create new one
                            pass
                        elif active_bitfield and ( row['offset'] % 8 == 0):
                            # We /WERE/ in a bitfield,
                            # but have rolled over to a new octet
                            active_bitfield = False
                            bfname = "ERROR"
                            # The code block below will now catch this and begin new bitfield

                        # Now bring the offset where it should be
                        bitoffset = row['offset']
                # (end while)

                if row['bits'] < 8:
                    # deal with bit(s) in bitfield
                    if active_bitfield and ( row['offset'] % 8 == 0):
                        # We /WERE/ in a bitfield,
                        # but have rolled over to a new octet
                        active_bitfield = False
                        bfname = "ERROR"
                        # The code block below will now catch this and begin new bitfield

                    # This looks a little redundant or could be joined with prior if block
                    # but it is important that the "not active_bitfield" block below execute
                    # for both not active upon entry to block above but also in case
                    # the active_bitfield is set to False in the case above
                    if not active_bitfield:
                        active_bitfield = True
                        bitfield_num += 1
                        bfname = "bitfield" + str(bitfield_num)
                        field_struct += "B "
                        field_names.append( bfname )
                        fields[bfname] = Field(id=bfname, type="bitfield")
                    # < 8 bits: No need to insert into the field_struct for unpacking
                    # < 8 bits: No need to insert into the field names list for unpacking
                    # Create the Field obj but indicate it is part of a bitfield
                    fields[ bfname + ':' + row['id'] ] = Field(**row, zero_value=self.zero_value)
                elif row['bits'] == 8:
                    assert( row['offset'] % 8 == 0 )    # Sanity check that we are aligned
                    field_struct += "B "
                    field_names.append( row['id'] )
                    fields[ row['id'] ] = Field(**row, zero_value=self.zero_value)
                elif row['bits'] > 8 and ( row['bits'] % 8 == 0):
                    # This will apply equally to ints, strings, BCD
                    field_struct += "{:d}s ".format( row['bits'] // 8 )
                    field_names.append( row['id'] )
                    fields[ row['id'] ] = Field(**row, zero_value=self.zero_value)
                else:
                    raise ValueError("bits > 8 but not apparently an even no. of octets")
                
                # Don't forget to advance the offset counter
                bitoffset += row['bits']

                # This is the best place, as far as I can tell, to check if we rolled over
                # to a new octet, just in case we were in a bitfield, and enter a new one
                if (bitoffset % 8) == 0:
                    active_bitfield = False
                    bitfield_name = "ERROR"

        if DEBUG:
            print("finished reading csv")
            print( field_names )
            print( field_struct )
            print( fields )
            print()
        #pdb.set_trace()
        self.field_names = field_names
        self.field_struct_string = field_struct
        self.fields = fields

    def _expand_bitfields(self, k, v, fieldset):
        """Automatically fill in fields from a bitfield
        
        Take a key/value pair and check if it is bitfield type.
        If yes, search through fieldset for its constituents
        and expand it into them. Return True to signal ok to delete.

        If no, return False and move on.
        """
        if len(k) < 8: return False   # Not bitfield
        elif k[0:8] == "bitfield" and ':' not in k:
            # k is a raw bitfield and not a bitfield:subfield
            bfnum = int( k[8:] )
            # Find subfields that are a part of this bitfield
            for fid,field in fieldset.items():
                if field.type == 'bitfield': continue    # raw bitfield -- we are looking for subfields
                # ex:
                # k = bitfield7
                # v = raw bitfield
                # fid = "bitfield7:realfield_name"
                # field = realfield's data (initially uninitialized)
                if fid.startswith(k):
                    # Okay, now decompose v
                    lsbit_within_octet = field.offset % 8   # zero indexed
                    # make bitmask in lsb positions and then shift left
                    bitmask = ((2 ** field.bits) - 1) << lsbit_within_octet
                    field.value = (v & bitmask) >> lsbit_within_octet

            return True
        else:
            # Any other type of field, including subfield of bitfield
            return False
    
    def _rename_bitfield_subfields(self, fieldset):
        """Remove the leading 'bitfieldN:' from bitfield subfields
        
        By this point there should be no type:bitfield raw bitfields left,
        so it is okay to check for [0:8] == bitfield
        """
        if DEBUG:
            print("_rename_bitfield_subfields()")
            print( fieldset )
            pdb.set_trace()
            print( list( fieldset.items() ) )
        # We can't rename keys during iteration
        rename_list = []
        for fid, field in fieldset.items():
            if len(fid) < 8: continue
            if fid[0:8] == "bitfield":
                rename_list.append(fid)

        for fid in rename_list:
            fn_pos = fid.index(':') + 1
            subfield_name = fid[fn_pos:]    # take everything after the :
            # Okay, we must rename two things:
            # (1) key in the fieldset dict
            # (2) the field's 'id' property
            fieldset[subfield_name] = fieldset.pop(fid)
            fieldset[subfield_name].id = subfield_name
        
        return fieldset

    def _record_is_deleted(self, data):
        if data[self.deletion_marker_offset] == self.deletion_marker_value:
            return True
        else:
            return False
        
    def add_lut(self, fieldid, lut):
        self.fields[fieldid].add_lut(lut)

    def load(self, data):
        print("Table::load()")
        self.field_struct = struct.Struct(self.field_struct_string)

        self.rows = []
        for i in range(self.num_records):
            if DEBUG:
                print("i=", i)
                print(self.fields)
                pdb.set_trace()
            ###fieldset = copy.deepcopy(self.fields)
            row = Row(self.fields)
            # TODO subset the data outside of here
            current_record_offset   = self.first_record_offset + (self.record_length * i)
            current_record_end      = current_record_offset + self.record_length

            # Check for deletion marker:
            row['deleted'] = self._record_is_deleted( data[current_record_offset: current_record_end] )
            
            if DEBUG: print("DEBUG: field_struct_string=", self.field_struct_string)
            field_values =  self.field_struct.unpack( data[ current_record_offset:current_record_end ] )
            fields_raw = dict(zip(self.field_names, field_values))
            if DEBUG: print("fields_raw=", fields_raw)

            # Once a bitfield is expanded into its consituent subfields, mark for deletion
            deletion_list = []
            for k,v in fields_raw.items():
                if DEBUG: print("k,v=", k, v)
                if self._expand_bitfields(k, v, row):
                    # Has been expanded completely -- okay to remove (but not during iteration)
                    deletion_list.append(k)
                ###fieldset[k].value = v
                row[k].value = v
                ###fieldset[k].validate()
                row[k].validate()

            # Remove the raw bitfields
            for k in deletion_list:
                ###del fieldset[k]
                del row[k]
            # Strip the leading "bitfieldN:" from subfield ids
            ###fieldset = self._rename_bitfield_subfields(fieldset)
            row = self._rename_bitfield_subfields(row)

            if DEBUG:
                print("fieldset post load =")
                pprint.pprint( fieldset )
                #pdb.set_trace()
            ###self.rows.append( fieldset )
            self.rows.append( row )
    
    def dump(self):
        pass
    
    def __init__(self, tabledef_fn):
        self._read_fields(tabledef_fn)
        #self._expand_bitfields()

class Channel(Table):
    tabledef_fn = "fields_channel.csv"
    num_records = 1000
    first_record_offset = 127013
    record_length = 64
    end_record_offset = first_record_offset + record_length
    zero_value = 0xFF

    deletion_marker_offset  = 16    # bytes
    deletion_marker_value   = 0xFF

    #channel_struct = struct.Struct("<c c c c c x h c B c B B x c x 4s 4s 2s 2s c c x x 32s")
    def __init__(self):
        print("Channel init")
        super().__init__(Channel.tabledef_fn)

class Settings(Table):
    tabledef_fn = "fields_settings.csv"
    num_recods = 1
    first_record_offset = 8805
    record_length = 144
    zero_value = 0xFF

    deletion_marker_offset  = 0x00  # Not really sure best way to do this,
    deletion_marker_value   = 0x01  # since Settings has only one row / can't be del'd

    def __init__(self):
        print("General init")
        super().__init__(Settings.tabledef_fn)

        # At this point the RDT file has not been loaded, 
        # so bitfield-subfield fields have not been renamed yet
        # Solution is to (1) either include RDT file as part of __init__
        # (2) have the Table.add_lut function do additional lookup prefixing with bitfieldNN:
        # (3) change the bitfieldN prperty to some other metadata field, (i.e. not encoded in the name) or
        # (4) add the LUT after RDT file loaded (bad choice due to having to add it to 1000 separate fields)
        #self.add_lut("monitor_type", {0: "silent", 1: "open"})
        #self.add_lut("talk_permit_tone", {0: "none", 1: "digital", 2: "analog", 3: "both"} )
        #self.add_lut("intro_screen", {0: "info strings", 1: "graphic"})
        self.add_lut("keypad_lock_time", {1: "5 sec", 2: "10 sec", 3: "15 sec", 255: "manual"})
        self.add_lut("mode", {0: "MR", 255: "CH" } )

class GeneralSettings(Table):
    tabledef_fn = "fields_settings.csv"
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

        super()._read_fields(self.tabledef_fn)

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

class RDTFile():
    def __init__(self, fn):
        self.settings = Settings()
        self.channels = Channel()

        with open(fn, "rb") as fi:
            file_contents = fi.read()
        
        self.settings.load(file_contents)
        self.channels.load(file_contents)

def record_prettyprint(record):
    #TODO need to specify field order somehow
    #TODO: is dict.values() deterministic for any fixed dict?
    field_id_lens   = [len(field.id) for field in record.values()]
    field_descr_lens= [len(field.description) for field in record.values()]
    max_id_width    = max(field_id_lens)
    max_descr_width = max(field_descr_lens)
    print("{id:{width_id}s} {descr:{width_descr}s} Value".format(id="key", width_id=max_id_width, descr="Description", width_descr=max_descr_width))
    print("-"*80)
    for field in record.values():
        print("{id:{width_id}s} {descr:{width_descr}s} {repr}".format(\
            id=field.id, width_id=max_id_width, \
            descr=field.description, width_descr=max_descr_width, \
            repr=field))

def prettyprint_table(rows, field_names = ['name']):
    """Pretty print a table, but only a limited subset of fields."""
    # TODO: hardcoded no. of digits id
    format_string = "{:04d}\t"
    format_string += "{:20.20s} " * len(field_names)

    print("#\t" + ("{:20.20s} "*len(field_names)).format(*field_names) )
    print("-"*80)
    for i,row in enumerate(rows):
        if not row['deleted']:
            # row will be a fieldset, a dict of fields keyed on id
            field_values = [str(row[k]) for k in field_names]
            # if not row['deleted']:
            print( format_string.format(i+1, *field_values) )   # ids are 1-indexed :-/

def main():
    parser = argparse.ArgumentParser(description = "Read and write RDT codeplug files")
    parser.add_argument("-f", "--file", help="RDT codeplug file")
    subparsers = parser.add_subparsers(dest="subparser_name", help="Subcommand help")

    settings_cmd = subparsers.add_parser("settings", help="General radio settings")
    settings_cmd.add_argument("subcommand", choices=['get','set'], help="What to do with settings")
    settings_cmd.add_argument("field", help="get: <field|all> | set: <field=value>")

    channels_cmd = subparsers.add_parser("channels", help="Radio channel settings")
    channels_cmd.add_argument("subcommand", choices=['list', 'export', 'import'], help="What to do with radio channels")
    
    args = parser.parse_args()

    rdtfile = RDTFile(args.file)

    if args.subparser_name == "settings":
        if args.subcommand == "get":
            if args.field == "all":
                record_prettyprint( rdtfile.settings.rows[0] )
            elif args.field:
                if args.field in rdtfile.settings.field_names:
                    print("{}\t{}".format(args.field, rdtfile.settings.rows[0][args.field]))
                else:
                    print("{} is not a valid field key name.\n\nChoices: {}".format(\
                        args.field, rdtfile.settings.field_names))
            else:
                print("TODO: print usage -- get <fieldname|all> (should have been caught by parser though)")
        elif args.subcommand == "set":
            print("TODO: Set a field and write back file")
        else:
            raise ValueError("subcommand neither get nor set -- should have been caught by arg parser")
        
    elif args.subparser_name == "channels":
        if args.subcommand == "list":
            prettyprint_table( rdtfile.channels.rows, ['name', 'contact_name'] )
        else:
            print("Not implemented.")

    else:
        print("Unknown subcommand {}".format(args.subparser_name))
        return 1

    return 0

if __name__ == "__main__":
    main()