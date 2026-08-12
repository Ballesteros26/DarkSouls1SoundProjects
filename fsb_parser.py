import sys
import struct
from enum import Enum, unique
import copy
import uuid
import binascii

import logging
log = logging.getLogger(__name__)

# Consumes length copies of byte from content, starting at offset.
# Returns the new offset after consumption.
# Raises a ValueError if any of the consumed bytes do not match the
#  given value. 
def consume_byte(content, offset, byte, length=1):
    for i in range(0, length-1):
        if content[offset + i:offset + i+1] != byte:
            raise ValueError(("Expected byte '0x%s' at offset " + 
             "0x%x but received byte '0x%s'.") % (byte.hex(), offset+i, 
             content[offset + i:offset + i+1].hex()))
    return offset + length
    
# Wrapper for struct.unpack_from to make calculating offsets easier.
#  Returns (result, new_offset) where result is the output of struct.unpack_from.
def extract_struct(format_string, content, offset=0):
    result = struct.unpack_from(format_string, content, offset=offset)
    return (result, offset + struct.calcsize(format_string))
    
# Extracts a NUL-terminated string from content. The string is stored at offset
#  with a 32-bit unsigned integer first to determine the length of the string, followed
#  by the string.
def extract_length_and_strz(content, offset=0):
    ((name_length,), offset) = extract_struct("<I", content, offset=offset)
    ((name,), offset) = extract_struct(str(name_length) + "s", content, offset=offset)
    name = name[:-1].decode("utf-8") # Remove trailing \x00 and convert to str
    return (name, offset)
    
# Generates a new random UUID to use as a fresh FMOD GUID.
def get_new_guid():
    return str(uuid.uuid4())
    

# A representation of wavetable data that is written to the .fsb.
class FSBSample():
    NAME_LENGTH = 30
    
    @unique
    class FSBSampleMode(Enum):
        FSOUND_LOOP_OFF = 0x00000001
        FSOUND_LOOP_NORMAL= 0x00000002
        FSOUND_LOOP_BIDI= 0x00000004
        FSOUND_8BITS = 0x00000008
        FSOUND_16BITS = 0x00000010
        FSOUND_MONO = 0x00000020
        FSOUND_STEREO = 0x00000040
        FSOUND_UNSIGNED = 0x00000080
        FSOUND_SIGNED = 0x00000100
        FSOUND_MPEG = 0x00000200
        FSOUND_CHANNELMODE_ALLMONO = 0x00000400
        FSOUND_CHANNELMODE_ALLSTEREO = 0x00000800
        FSOUND_HW3D = 0x00001000
        FSOUND_2D = 0x00002000
        FSOUND_SYNCPOINTS_NONAMES = 0x00004000
        FSOUND_DUPLICATE = 0x00008000
        FSOUND_CHANNELMODE_PROTOOLS = 0x00010000
        FSOUND_MPEGACCURATE = 0x00020000
        FSOUND_MPEG_LAYER2 = 0x00040000
        FSOUND_HW2D = 0x00080000
        FSOUND_3D = 0x00100000
        FSOUND_32BITS = 0x00200000
        FSOUND_IMAADPCM = 0x00400000
        FSOUND_VAG = 0x00800000
        FSOUND_XMA = 0x01000000
        FSOUND_GCADPCM = 0x02000000
        FSOUND_MULTICHANNEL = 0x04000000
        FSOUND_OGG = 0x08000000
        FSOUND_MPEG_LAYER3 = 0x10000000
        FSOUND_IMAADPCMSTEREO = 0x20000000
        FSOUND_IGNORETAGS = 0x40000000
        FSOUND_SYNCPOINTS = 0x80000000

    def __init__(self, sample_name, sample_length, compressed_length,
     loop_start, loop_end, mode_flags, deffreq, defvol, defpan, defpri,
     num_of_channels, min_dist, max_dist, varvol, varpan, metadata, data):
        self.sample_name = sample_name
        self.sample_length = sample_length
        self.compressed_length = compressed_length
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.mode_flags = mode_flags
        self.deffreq = deffreq
        self.defvol = defvol
        self.defpan = defpan
        self.defpri = defpri
        self.num_of_channels = num_of_channels
        self.min_dist = min_dist
        self.max_dist = max_dist
        self.varvol = varvol
        self.varpan = varpan
        self.metadata = metadata
        self.data = data
    
    # Read an FSB sample from content starting at offset, with audio data
    #  starting at data_offset.
    # Returns (sample, new_offset, new_data_offset).
    @classmethod
    def from_file_content(cls, content, offset, data_offset):
        master_offset = offset
        ((total_size,), master_offset) = extract_struct("<H", content, master_offset)
        ((sample_name_untrimmed,), master_offset) = extract_struct(str(FSBSample.NAME_LENGTH) + "s", 
            content, master_offset)
        sample_name = sample_name_untrimmed.rstrip(b"\x00").decode("utf-8")
        ((sample_length, compressed_length, loop_start, loop_end, mode_value),
            master_offset) = extract_struct("<IIIII", content, master_offset)            
        mode_flags = [flag for flag in FSBSample.FSBSampleMode if (flag.value & mode_value) == flag.value]
        ((deffreq, defvol, defpan, defpri, num_of_channels, min_dist, 
            max_dist, size_32bits, varvol, varpan), 
            master_offset) = extract_struct("<iHhHHffIHh", content, master_offset)
        metadata = content[master_offset : offset + total_size]
        
        data = content[data_offset : data_offset + compressed_length]
        
        return (FSBSample(sample_name, sample_length, compressed_length, 
            loop_start, loop_end, mode_flags, deffreq, defvol, defpan, 
            defpri, num_of_channels, min_dist, max_dist, varvol, varpan, 
            metadata, data), offset + total_size, data_offset + compressed_length)
    
    # Emit an XML representation of this FSB Sample for use in a FMOD 
    #  Designer Project file (.fdp). 
    # filepath is a path to the sample's file, found by parsing a corresponding
    #  .fev file.
    def to_xml_string(self, filepath=""):
        return_list = []
        return_list.append("<waveform>")
        
        if filepath != "":
            filename = filepath.split("/")[-1]
            if filename != self.sample_name:
                raise ValueError("Mismatch between filename in submitted waveform filepath \'" + 
                    filepath + "\' and true filename \'" + self.sample_name + "\'. Error suspected.")
        else:
            filepath = self.sample_name
        
        return_list.append("<filename>" + filepath + "</filename>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list.append("<mindistance>" + str(self.min_dist) + "</mindistance>")
        return_list.append("<maxdistance>" + str(self.max_dist) + "</maxdistance>")
        return_list.append("<deffreq>" + str(self.deffreq) + "</deffreq>")
        return_list.append("<defvol>" + str(self.defvol) + "</defvol>")
        return_list.append("<defpan>" + str(self.defpan) + "</defpan>")
        return_list.append("<defpri>" + str(self.defpri) + "</defpri>")
        return_list.append("<xmafiltering>0</xmafiltering>")
        
        # Attempt to compute channel mode from the mode flags. This is
        #  not comprehensive, because this was not assumed to be needed
        #  so the channel mode is a menu index rather than independent
        #  of other settings.
        channelmode = 0
        if (FSBSample.FSBSampleMode.FSOUND_STEREO in self.mode_flags and 
         FSBSample.FSBSampleMode.FSOUND_CHANNELMODE_ALLMONO in self.mode_flags):
            channelmode = 1
        if (FSBSample.FSBSampleMode.FSOUND_MULTICHANNEL in self.mode_flags and
         FSBSample.FSBSampleMode.FSOUND_CHANNELMODE_ALLMONO in self.mode_flags):
             channelmode = 1
        if (FSBSample.FSBSampleMode.FSOUND_MULTICHANNEL in self.mode_flags and
         FSBSample.FSBSampleMode.FSOUND_CHANNELMODE_ALLSTEREO in self.mode_flags):
             channelmode = 2
        if (FSBSample.FSBSampleMode.FSOUND_MULTICHANNEL in self.mode_flags and 
         FSBSample.FSBSampleMode.FSOUND_CHANNELMODE_PROTOOLS in self.mode_flags):
             channelmode = 3
        return_list.append("<channelmode>" + str(channelmode) + "</channelmode>")

        return_list.append("<quality_crossplatform>0</quality_crossplatform>")
        return_list.append("<quality>-1</quality>")
        return_list.append("<optimisedratereduction>100</optimisedratereduction>")
        return_list.append("<enableratereduction>1</enableratereduction>")
        return_list.append("<notes></notes>")
        return_list.append("</waveform>")
        return return_list
        
    # Emit a string list representation of the FSB Sample.
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append("Sample[name=\'%s\', sample_length=%d, comp_length=%d, ..." %
            (self.sample_name, self.sample_length, self.compressed_length))
        return_list.append(" loop_start=%d, loop_end=%d, deffreq=%d, defvol=%d, defpan=%d, ..." %
            (self.loop_start, self.loop_end, self.deffreq, self.defvol, self.defpan))
        return_list.append(" defpri=%d, num_of_channels=%d, min_dist=%f, ..." %
            (self.defpri, self.num_of_channels, self.min_dist))
        return_list.append(" max_dist=%f, varvol=%d, varpan=%d, metadata=%s" % 
            (self.max_dist, self.varvol, self.varpan, binascii.hexlify(self.metadata).decode("utf-8")))
        mode_flag_string = ", ".join([str(m) for m in self.mode_flags])
        return_list.append(" mode_flags=[%s]]" % mode_flag_string)
        return return_list
           

# A representation of the structure of a FMOD Sound Bank (.fsb) file.
class FSBStruct():
    @unique
    class FSBHeaderMode(Enum):
        FORMAT = 0x01
        BASICHEADERS = 0x02
        ENCRYPTED = 0x04
        BIGENDIANPCM = 0x08
        NOTINTERLEAVED = 0x10
        MPEG_PADDED = 0x20
        MPEG_PADDED4 = 0x40    
    
    @unique
    class FSBHeaderVersion(Enum):
        VERSION_3_0 = 0x00030000
        VERSION_3_1 = 0x00030001
        VERSION_4_0 = 0x00040000
    
    def __init__(self, version, mode_flags, bank_hash, guid, samples):
        self.version = version 
        self.mode_flags = mode_flags
        self.bank_hash = bank_hash
        self.guid = guid
        self.samples = samples
    
    # Read an .fsb file, saved in content, starting at offset.
    # Returns the parsed struct.
    @classmethod
    def from_file_content(cls, content, offset=0):
        master_offset = offset 
        
        # Read header information
        master_offset = consume_byte(content, master_offset, b"F")
        master_offset = consume_byte(content, master_offset, b"S")
        master_offset = consume_byte(content, master_offset, b"B")
        master_offset = consume_byte(content, master_offset, b"4")
        ((num_of_samples, total_header_size, sample_data_size, version_value,
            mode_value), master_offset) = extract_struct("<iIIII", content, master_offset)
        mode_flags = [flag for flag in FSBStruct.FSBHeaderMode if (flag.value & mode_value) == flag.value]
        version = FSBStruct.FSBHeaderVersion(version_value)
        ((bank_hash,), master_offset) = extract_struct(">Q", content, master_offset)
        ((guid_chunk1, guid_chunk2, guid_chunk3), 
            master_offset) = extract_struct("<4s2s2s", content, master_offset)
        ((guid_chunk4, guid_chunk5), 
            master_offset) = extract_struct("<2s6s", content, master_offset)
        # Reverse the first three chunks and hexify all chunks to build the GUID string
        guid = "-".join([guid_chunk1[::-1].hex(), guid_chunk2[::-1].hex(),
            guid_chunk3[::-1].hex(), guid_chunk4.hex(), guid_chunk5.hex()])
            
        current_data_offset = master_offset + total_header_size
        file_size = current_data_offset + sample_data_size
        
        samples = []
        for i in range(num_of_samples):
            if FSBStruct.FSBHeaderMode.BASICHEADERS in mode_flags and i > 0:
                sample = copy.deepcopy(samples[0])
                ((sample.sample_length, sample.compressed_length),
                    master_offset) = extract_struct("<II", content, master_offset)
            else:
                (sample, master_offset, current_data_offset) = \
                    FSBSample.from_file_content(content, master_offset, current_data_offset)
            samples.append(sample)
        if current_data_offset != file_size:
            raise ValueError("Mismatch between consumed data offset (" + 
                str(current_data_offset) + ") and expected data offset (" +
                str(file_size) + ").")
            
        return FSBStruct(version, mode_flags, bank_hash, guid, samples)
    
    # Returns a string list representation of the struct.
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append("FSBStruct[version=%s, hash=%#018x, ..." %
            (self.version, self.bank_hash))
        return_list.append(" guid=%s, ..." % self.guid)
        mode_flag_string = ", ".join([str(m) for m in self.mode_flags])
        return_list.append(" mode_flags = [%s]]" % mode_flag_string)
        for sample in self.samples:
            return_list += ["  " + line for line in sample.to_string()]
        return return_list
        
if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Usage: " + sys.argv[0] + " <FSB File>")
    else:
        with open(sys.argv[1], "rb") as f:
            content = f.read()
            fsb_data = FSBStruct.from_file_content(content)
            print("\n".join(fsb_data.to_string()))
