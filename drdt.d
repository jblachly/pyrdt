import std.bitmanip;
import std.file;

// http://forum.dlang.org/thread/eiquqszzycomrcazcfsb@forum.dlang.org
// http://www.iz2uuf.net/wp/index.php/2016/06/04/tytera-dm380-codeplug-binary-format/

struct ChannelInformation
{

}

struct DigitalContact
{

}

struct DigitalRxGroupList
{

}

struct GeneralSettings
{

}

struct ScanList
{
    wchar name[16];     // 32 octets

}

struct TextMessage
{
    wchar message[144]; // 288 octents
}

struct ZoneInfo
{
    wchar name[16];     // 32 octets
    ushort channelid[16];
}

