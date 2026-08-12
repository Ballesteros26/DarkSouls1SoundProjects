import sys
import struct
from enum import Enum, unique
import uuid
import math

import fev_parser_xml_const

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

# Converts a field ratio to its corresponding decibel value.
#  Value is clamped to -60 at minimum to prevent log(0) errors.
def field_ratio_to_decibel(field_ratio):
    if field_ratio <= 0.001:
        return -60
    return 20*math.log10(field_ratio)
    
# Helper function to implement ternary-like string switching.
def bool_to_string(bool_to_use, true_string, false_string):
    if bool_to_use:
        return true_string
    else:
        return false_string


# Wavebank information from the Banks view.
class WavebankInfo:
    @unique
    class BankType(Enum):
        STREAM_FROM_DISK = 0x0080
        LOAD_INTO_MEM = 0x0200
        DECOMP_INTO_MEM = 0x0100
        
        def to_xml_name(self):
            xml_name_dict = {
                self.STREAM_FROM_DISK: "Stream",
                self.LOAD_INTO_MEM: "Sample",
                self.DECOMP_INTO_MEM: "DecompressedSample"}
            return xml_name_dict[self]
            
    @unique
    class BankOutputFormat(Enum):
        PCM = 0
        ADPCM = 1
        MP3 = 2
        MP2 = 3
    
    def __init__(self, bank_type, max_streams, bank_hash, bank_name):
        self.bank_type = bank_type
        self.max_streams = max_streams
        self.bank_hash = bank_hash
        self.bank_name = bank_name 
    
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse WaveBankInfo @ %#010x" % offset)
        master_offset = offset
        ((bank_type, max_streams), 
            master_offset) = extract_struct("<II", content, offset=master_offset)
        ((bank_hash,), 
            master_offset) = extract_struct(">Q", content, offset=master_offset)
        (bank_name, master_offset) = extract_length_and_strz(content, master_offset)
        return (WavebankInfo(WavebankInfo.BankType(bank_type), max_streams, 
            bank_hash, bank_name), master_offset)
    
    # Emits a representation of the Wavebank information as a string.
    def to_string(self):
        return ("WaveBank[name=\'%s\', type=%s, max_streams=%d, hash=%#018x]" %
            (self.bank_name, self.bank_type, self.max_streams, self.bank_hash))
    
    # Emits a string list representation of the leading chunk of the wavebank's data in the .fdp.
    # This chunk is then followed by information about the wavebank's samples
    #  derived from the .fsb, and then by the output of to_xml_string_footer.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string_header(self):
        return_list = []
        return_list.append("<soundbank>")
        return_list.append("<name>" + self.bank_name + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list += fev_parser_xml_const.WAVEBANK_HEADER_OPTIONS.splitlines()
        return_list.append("<_PC_banktype>" + self.bank_type.to_xml_name() + "</_PC_banktype>")
        return_list += fev_parser_xml_const.WAVEBANK_UNUSED_BANKTYPE.splitlines()
        return return_list
     
    # Emits a string list representation of the closing chunk of the wavebank's data in the .fdp.
    # bank_format is a value from WavebankInfo.BankOutputFormat and is determined by data
    #  from the wavebank's samples, derived from the .fsb.
    # This chunk is preceeded by other data, see to_xml_string_header.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string_footer(self, bank_output_format):
        return_list = []
        return_list.append("<_PC_format>" + bank_output_format.name + "</_PC_format>")
        return_list.append("<_PC_quality>50</_PC_quality>")
        return_list.append("<_PC_optimisesamplerate>0</_PC_optimisesamplerate>")
        return_list.append("<_PC_forcesoftware>1</_PC_forcesoftware>")
        return_list.append("<_PC_maxstreams>" + str(self.max_streams) + "</_PC_maxstreams>")
        return_list += fev_parser_xml_const.WAVEBANK_UNUSED_QUALITY.splitlines()
        return_list.append("</soundbank>")
        return return_list
        
    
# Event category from the Events view, in the Event Categories pane.
# Used to organize Events for compile-time mixing, as opposed to
#  Event Groups, which are used to organize Events for runtime referencing.
class EventCategory:
    @unique
    class PlaybackBehavior(Enum):
        STEAL_OLDEST = 0
        STEAL_NEWEST = 1
        STEAL_QUIETEST = 2
        JUST_FAIL = 3
        JUST_FAIL_IF_QUIETEST = 4
        
        def to_xml_name(self):
            xml_name_dict = {
                self.STEAL_OLDEST: "Steal_oldest",
                self.STEAL_NEWEST: "Steal_newest",
                self.STEAL_QUIETEST: "Steal_quietest",
                self.JUST_FAIL: "Just_fail",
                self.JUST_FAIL_IF_QUIETEST: "Just_fail_if_quietest"}
            return xml_name_dict[self]
            
        
    def __init__(self, name, volume, pitch, max_playbacks, 
     max_playback_behavior, subcategories):
        self.name = name
        self.volume = volume
        self.pitch = pitch
        self.max_playbacks = max_playbacks
        self.max_playback_behavior = max_playback_behavior
        self.subcategories = subcategories
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse EventCategory @ %#010x" % offset)
        master_offset = offset
        (cat_name, master_offset) = extract_length_and_strz(content, master_offset)
        ((cat_volume, cat_pitch, cat_max_playbacks, cat_playback_behavior, 
            cat_num_of_subcats), master_offset) = extract_struct("<ffIII", content, master_offset)
        cat_subcategories = []
        for _ in range(cat_num_of_subcats):
            (subcat, master_offset) = EventCategory.from_file_content(content, master_offset)
            cat_subcategories.append(subcat)
        return (EventCategory(cat_name, cat_volume, cat_pitch, 
            cat_max_playbacks, EventCategory.PlaybackBehavior(cat_playback_behavior),
            cat_subcategories), master_offset)
    
    # Emits a string list representation of the Event Category -- including
    #  all subcategories.
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append(("EventCategory[name=\'%s\', volume=%f, pitch=%f, " + 
            "max_playbacks=%d, max_playback_behavior=%s]") % 
            (self.name, self.volume, self.pitch, self.max_playbacks,
            self.max_playback_behavior))
        if len(self.subcategories) > 0:
            for sc in self.subcategories:
                sc_string_list = sc.to_string()
                for line in sc_string_list:
                    return_list.append(" " + line)
        return return_list
    
    # Emits a string list representation of the Event Category -- including
    #  all subcategories -- as represented in the .fdp.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string(self):
        return_list = []
        return_list.append("<eventcategory>")
        return_list.append("<name>" + self.name + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list.append("<volume_db>" + str(field_ratio_to_decibel(self.volume)) + "</volume_db>")
        return_list.append("<pitch>" + str(self.pitch * 4.0) + "</pitch>")
        return_list.append("<maxplaybacks>" + str(self.max_playbacks) + "</maxplaybacks>")
        return_list.append("<maxplaybacks_behavior>" + self.max_playback_behavior.to_xml_name() + "</maxplaybacks_behavior>")
        return_list.append("<notes></notes>")
        return_list.append("<open>0</open>")
        if len(self.subcategories) > 0:
            for sc in self.subcategories:
                return_list += sc.to_xml_string()
        return_list.append("</eventcategory>")
        return return_list
        
# User Property that can be attached to Layers, Event Groups, etc.
# Used to store user data that is referenced by the game's code (by name).
class UserProperty():
    @unique
    class PropertyType(Enum):
        INTEGER = 0
        FLOATING_POINT = 1
        STRING = 2
        
    def __init__(self, prop_name, prop_type, prop_value):
        self.prop_name = prop_name
        self.prop_type = prop_type
        self.prop_value = prop_value
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse UserProperty @ %#010x" % offset)
        master_offset = offset
        (prop_name, master_offset) = extract_length_and_strz(content, master_offset)
        ((prop_type_value,), master_offset) = extract_struct("<I", content, master_offset)
        prop_type = UserProperty.PropertyType(prop_type_value)
        if prop_type == UserProperty.PropertyType.INTEGER:
            ((prop_value,), master_offset) = extract_struct("<i", content, master_offset)
        elif prop_type == UserProperty.PropertyType.FLOATING_POINT:
            ((prop_value,), master_offset) = extract_struct("<f", content, master_offset)
        elif prop_type == UserProperty.PropertyType.STRING:
            (prop_value, master_offset) = extract_length_and_strz(content, master_offset)
        else:
            raise TypeError("Unhandled UserProperty PropertyType: Received %s" % prop_type)
        
        return (UserProperty(prop_name, prop_type, prop_value), master_offset)
    
    # Emits a string representation of the User Property.
    def to_string(self):
        prop_value_as_str = ""
        if self.prop_type == UserProperty.PropertyType.INTEGER:
            prop_value_as_str = "%d" % self.prop_value
        elif self.prop_type == UserProperty.PropertyType.FLOATING_POINT:
            prop_value_as_str = "%f" % self.prop_value
        elif self.prop_type == UserProperty.PropertyType.STRING:
            prop_value_as_str = "\'%s\'" % self.prop_value
        else:
            prop_value_as_str = "UNKNOWN"
        return ("UserProperty[name=\'%s\', type=%s, value=%s]" % 
            (self.prop_name, self.prop_type, prop_value_as_str))
    
    # Emits a string list representation of the User Property as in the .fdp.
    # Each element of the list corresponds to a line in the representation.        
    def to_xml_string(self):
        return_list = []
        return_list.append("<userproperty>")
        return_list.append("<name>" + str(self.prop_name) + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list.append("<description></description>")
        if self.prop_type == UserProperty.PropertyType.INTEGER:
            return_list.append("<data_int>" + str(self.prop_value) + "</data_int>")
        elif self.prop_type == UserProperty.PropertyType.FLOATING_POINT:
            return_list.append("<data_float>" + str(self.prop_value) + "</data_float>")
        elif self.prop_type == UserProperty.PropertyType.STRING:
            return_list.append("<data_string>" + self.prop_value + "</data_string>")
        return_list.append("</userproperty>")
        return return_list
            

# Sound Definition Instance included on Layers in Events.
# Each Sound Definition Instance is an occurance of a base Sound Definition.
class SoundDefInstance():
    @unique
    class StartMode(Enum):
        IMMEDIATE = 0
        WAIT_FOR_END = 1
    
    @unique
    class LoopMode(Enum):
        LOOP_AND_CUTOFF = 0
        ONESHOT = 1
        LOOP_AND_PLAY_TO_END = 2
    
    @unique
    class AutopitchParameter(Enum):
        EVENT_PRIMARY = 0
        LAYER_CONTROL = 2
        
        def to_xml_name(self):
            xml_name_dict = {
                self.EVENT_PRIMARY: "0",
                self.LAYER_CONTROL: "1"}
            return xml_name_dict[self]
        
    @unique
    class CrossfadeType(Enum):
        BEZIER = 0
        LINEAR = 1
        RAISED = 2
        POWER_05_MID = 3
        POWER_30_MID = 4
        POWER_45_MID = 5
        POWER_30_LATE = 6
        POWER_30_EARLY = 7
        
    def __init__(self, sound_index, sound_start, sound_length, start_mode,
     loop_mode, autopitch_param, loop_count, autopitch_enabled, 
     autopitch_reference, autopitch_at_min, fine_tune, volume,
     fade_in_length, fade_out_length, fade_in_type, fade_out_type):
        self.sound_index = sound_index
        self.sound_start = sound_start
        self.sound_length = sound_length
        self.start_mode = start_mode
        self.loop_mode = loop_mode
        self.autopitch_param = autopitch_param
        self.loop_count = loop_count
        self.autopitch_enabled = autopitch_enabled
        self.autopitch_reference = autopitch_reference
        self.autopitch_at_min = autopitch_at_min
        self.fine_tune = fine_tune
        self.volume = volume
        self.fade_in_length = fade_in_length
        self.fade_out_length = fade_out_length
        self.fade_in_type = fade_in_type
        self.fade_out_type = fade_out_type
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse SoundDefInstance @ %#010x" % offset)
        master_offset = offset 
        ((sound_index, sound_start, sound_length), 
            master_offset) = extract_struct("<Hff", content, master_offset)
        ((start_mode_value, loop_mode_value, autopitch_param_value),
            master_offset) = extract_struct("<IBB", content, master_offset)
        start_mode = SoundDefInstance.StartMode(start_mode_value)
        loop_mode = SoundDefInstance.LoopMode(loop_mode_value)
        autopitch_param = SoundDefInstance.AutopitchParameter(autopitch_param_value)
        master_offset = consume_byte(content, master_offset, b"\x00", 2)
        ((loop_count, autopitch_enabled_value, autopitch_reference,
            autopitch_at_min, fine_tune, volume), 
            master_offset) = extract_struct("<iIffff", content, master_offset)
        autopitch_enabled = (autopitch_enabled_value == 1)
        ((fade_in_length, fade_out_length, fade_in_type_value, fade_out_type_value),
            master_offset) = extract_struct("<ffII", content, master_offset)
        fade_in_type = SoundDefInstance.CrossfadeType(fade_in_type_value)
        fade_out_type = SoundDefInstance.CrossfadeType(fade_out_type_value)
        return (SoundDefInstance(sound_index, sound_start, sound_length, 
            start_mode, loop_mode, autopitch_param, loop_count, 
            autopitch_enabled, autopitch_reference, autopitch_at_min, 
            fine_tune, volume, fade_in_length, fade_out_length, 
            fade_in_type, fade_out_type), master_offset)
    
    # Emits a string list representation of the SoundDefInstance.
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append("SoundDefInstance[sound_index=%d, start=%f, length=%f, start_mode=%s, ..." %
            (self.sound_index, self.sound_start, self.sound_length, self.start_mode))
        return_list.append(" loop_mode=%s, autopitch_param=%s, loop_count=%d, autopitch_enabled=%s, ..." %
            (self.loop_mode, self.autopitch_param, self.loop_count, self.autopitch_enabled))
        return_list.append(" autopitch_reference=%f, autopitch_at_min=%f, fine_tune=%d, ..." %
            (self.autopitch_reference, self.autopitch_at_min, self.fine_tune))
        return_list.append(" volume=%f, fade_in_length=%f, fade_out_length=%f, ..." %
            (self.volume, self.fade_in_length, self.fade_out_length))
        return_list.append(" fade_in_type=%s, fade_out_type=%s]" %
            (self.fade_in_type, self.fade_out_type))
        return return_list
    
    # Emits a string list representation of the SoundDefInstance as it
    #  appears in the .fdp.
    # sounddefs is the list of SoundDefs found in the .fev that this SoundDefInstance
    #  is parsed from. SoundDefInstances index this list to determine data
    #  about the SoundDef they are an instance of.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string(self, sounddefs):
        return_list = []
        return_list.append("<sound>")
        return_list.append("<name>" + sounddefs[self.sound_index].name + "</name>")
        return_list.append("<x>" + str(self.sound_start) + "</x>")
        return_list.append("<width>" + str(self.sound_length) + "</width>")
        return_list.append("<startmode>" + str(self.start_mode.value) + "</startmode>")
        return_list.append("<loopmode>" + str(self.loop_mode.value) + "</loopmode>")
        return_list.append("<loopcount2>" + str(self.loop_count) + "</loopcount2>")
        return_list.append("<autopitchenabled>" + 
            bool_to_string(self.autopitch_enabled, "1", "0") + 
            "</autopitchenabled>")
        return_list.append("<autopitchparameter>" + 
            self.autopitch_param.to_xml_name() + "</autopitchparameter>")
        return_list.append("<autopitchreference>" + 
            str(self.autopitch_reference) + "</autopitchreference>")
        return_list.append("<autopitchatzero>" + str(self.autopitch_at_min) + "</autopitchatzero>")
        return_list.append("<finetune>" + str(self.fine_tune) + "</finetune>")
        return_list.append("<volume>" + str(self.volume) + "</volume>")
        return_list.append("<fadeintype>" + str(self.fade_in_type.value) + "</fadeintype>")
        return_list.append("<fadeouttype>" + str(self.fade_out_type.value) + "</fadeouttype>")
        return_list.append("</sound>")
        return return_list
   
   
# An (x,y) tuple that is used to describe an Envelope.
class Point():
    @unique
    class CurveShape(Enum):
        FLAT_ENDED = 1
        LINEAR = 2
        LOGARITHMIC = 4
        FLAT_MIDDLE = 8
        
    def __init__(self, x, y, curve_shape_to_previous):
        self.x = x
        self.y = y
        self.curve_shape_to_previous = curve_shape_to_previous
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse Point @ %#010x" % offset)
        master_offset = offset 
        ((x, y, curve_shape_value), 
            master_offset) = extract_struct("<ffI", content, master_offset)
        curve_shape = Point.CurveShape(curve_shape_value)
        return (Point(x, y, curve_shape), master_offset)
    
    # Emits a string representation of the Point.
    def to_string(self):
        return ("Point[x=%f, y=%f, curve_shape_to_previous=%s]" % 
            (self.x, self.y, self.curve_shape_to_previous))
    
    # Emits a string representation of the Point as it appears in the .fdp.
    # index is the index of this Point in the list of Points attached
    #  to the parent Envelope.
    def to_xml_string(self, index):
        is_first = "0"
        if index == 0:
            is_first = "1"
        return "<point>" + ",".join([str(self.x), str(self.y), is_first, 
            str(self.curve_shape_to_previous.value)]) + "</point>"
    

# Attached to Layers by effects. Unlike what might be expected,
#  the effect type is saved as part of all its constituent Envelopes,
#  which are attached directly to the Layer, rather than Envelopes
#  being attached to the effect, which is then attached to the Layer 
#  itself.
class Envelope():
    @unique
    class EffectType(Enum):
        DSP_EFFECT = 0x0004
        VOLUME = 0x000c
        PITCH = 0x0014
        PAN = 0x0024
        SURROUND_PAN = 0x0048
        THREE_DIM_PAN_LEVEL = 0x0404
        THREE_DIM_SPEAKER_SPREAD = 0x0104
        OCCLUSION = 0x2004
        REVERB_LEVEL = 0x0204
        REVERB_BALANCE = 0x0804
        TIME_OFFSET = 0x0044
        SPAWN_INTENSITY = 0x1004
        
        def to_xml_name(self):
            xml_name_dict = {
                self.DSP_EFFECT: "",
                self.VOLUME: "Volume",
                self.PITCH: "Pitch",
                self.PAN: "Pan",
                self.SURROUND_PAN: "Surround pan",
                self.THREE_DIM_PAN_LEVEL: "3D Pan Level",
                self.THREE_DIM_SPEAKER_SPREAD: "3D Speaker spread",
                self.OCCLUSION: "Occlusion",
                self.REVERB_LEVEL: "Reverb Level",
                self.REVERB_BALANCE: "Reverb Balance",
                self.TIME_OFFSET: "Time offset",
                self.SPAWN_INTENSITY: "Spawn Intensity",}
            return xml_name_dict[self]
    
    def __init__(self, parent_index, name, effect_parameter_index, effect, 
     is_muted, flags, points, control_parameter_index, mapping_method):
        self.parent_index = parent_index
        self.name = name
        self.effect_parameter_index = effect_parameter_index
        self.effect = effect
        self.is_muted = is_muted
        self.flags = flags
        self.points = points
        self.control_parameter_index = control_parameter_index
        self.mapping_method = mapping_method
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse Envelope @ %#010x" % offset)
        master_offset = offset 
        
        ((parent_index,), master_offset) = extract_struct("<i", content, master_offset)
        (name, master_offset) = extract_length_and_strz(content, master_offset)
        ((effect_parameter_index, effect_and_mute), 
            master_offset) = extract_struct("<II", content, master_offset)
        effect = Envelope.EffectType(effect_and_mute & ~0x01 & 0xffff)
        is_muted = ((effect_and_mute & 0x01) == 0x01)
        flags = (effect_and_mute & ~0xffff)
        master_offset = consume_byte(content, master_offset, b"\x00", 4)
        ((num_of_points,), master_offset) = extract_struct("<I", content, master_offset)
        points = []
        for _ in range(num_of_points):
            (point, master_offset) = Point.from_file_content(content, master_offset)
            points.append(point)
        ((control_parameter_index, mapping_method,), 
            master_offset) = extract_struct("<II", content, master_offset)
        
        return (Envelope(parent_index, name, effect_parameter_index, effect, 
            is_muted, flags, points, control_parameter_index, 
            mapping_method), master_offset)
    
    # Emits a string list representation of the Envelope
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append("Envelope[parent_index=%d, name=\'%s\', effect_parameter_index=%d, ..." %
            (self.parent_index, self.name, self.effect_parameter_index))
        return_list.append(" effect=%s, is_muted=%s, flags=%d, control_parameter_index=%d, mapping_method=%d]" %
            (self.effect, self.is_muted, self.flags, self.control_parameter_index, self.mapping_method))
        for point in self.points:
            return_list.append("  " + point.to_string())
        return return_list
    
    # Emits a string list representation of the Envelope as it appears in the .fdp.
    # In normal use, effect envelopes are given a unique color upon creation,
    #  but this color is not important to the event data and is not saved in
    #  the .fev. Because of this, Envelopes all default to the same color
    #  which can then be manually set by the user should the need arise.
    # envelope_name is the name that this Envelope should be given in the
    #  .fdp data, since this name is not saved to the .fev and must be recreated.
    # envelopes is the list of all Envelopes attached to the Layer this
    #  Envelope is attached to. Envelopes are grouped into effects, and need
    #  to index this list to determine their master Envelope which holds
    #  the effect information.
    # parameters is the list of all Parameters attached to the Event to which
    #  this Envelope's Layer is attached. Envelopes are controlled by
    #  some Parameter, and index this list to determine information about
    #  that Parameter.
    # Each element of the list corresponds to a line in the representation.    
    def to_xml_string(self, envelope_name, envelopes, parameters):
        return_list = []
        return_list.append("<envelope>")
        return_list.append("<name>" + envelope_name + "</name>")
        envelope_to_use = self
        if self.parent_index != -1:
            envelope_to_use = envelopes[self.parent_index]
        dsp_name = envelope_to_use.name 
        if envelope_to_use.effect != Envelope.EffectType.DSP_EFFECT:
            dsp_name = envelope_to_use.effect.to_xml_name()
        return_list.append("<dsp_name>" + dsp_name + "</dsp_name>")
        return_list.append("<dsp_paramindex>" + str(self.effect_parameter_index) + "</dsp_paramindex>")
        # All envelopes have the same color, for simplicity.
        return_list.append("<colour>#7f0000</colour>")
        for (index, point) in enumerate(self.points):
            return_list.append(point.to_xml_string(index))
        return_list.append("<parametername>" + parameters[0].param_name + 
            "</parametername>")
        return_list.append("<controlparameter>" + 
            parameters[self.control_parameter_index].param_name +
            "</controlparameter>")
        return_list += fev_parser_xml_const.LAYER_ENABLES.splitlines()
        return_list.append("<mute>" + bool_to_string(self.is_muted, "1", "0") + "</mute>")
        return_list.append("<visible>1</visible>")
        return_list.append("<hidden>0</hidden>")
        return_list.append("<fromtemplate>No</fromtemplate>")
        return_list.append("<mappingmethod>" + str(self.mapping_method) + "</mappingmethod>")
        return_list.append("<flags>" + str(self.flags) + "</flags>")
        return_list.append("<exflags>0</exflags>")
        return_list.append("</envelope>")
        return return_list
            

# Holds Sound Definition Instances, so that a single event may play
#  several at the same time for the same control parameter value.
class Layer():
    def __init__(self, priority, control_parameter, 
     sound_definition_instances, envelopes):
        self.priority = priority
        self.control_parameter = control_parameter
        self.sound_definition_instances = sound_definition_instances
        self.envelopes = envelopes
        
    @classmethod
    def from_file_content(cls, content, offset, event_type):
        log.info("Parse Layer @ %#010x" % offset)
        master_offset = offset
        priority = -1
        control_parameter = -1
        if event_type == Event.EventType.COMPLEX:
            master_offset = consume_byte(content, master_offset, b"\x02")
            master_offset = consume_byte(content, master_offset, b"\x00")
            ((priority, control_parameter), 
                master_offset) = extract_struct("<hh", content, master_offset)
        ((num_of_sound_def_instances, num_of_envelopes), 
            master_offset) = extract_struct("<HH", content, master_offset)
        sound_definition_instances = []
        for _ in range(num_of_sound_def_instances):
            (sdi, master_offset) = SoundDefInstance.from_file_content(content, master_offset)
            sound_definition_instances.append(sdi)
        envelopes = []
        for _ in range(num_of_envelopes):
            (envelope, master_offset) = Envelope.from_file_content(content, master_offset)
            envelopes.append(envelope)
        return (Layer(priority, control_parameter, 
            sound_definition_instances, envelopes), master_offset)
    
    # Emits a string list representation of the Layer, including all
    #  attached SoundDefInstances and Envelopes.
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append("Layer[priority=%d, control_parameter=%d]" % 
            (self.priority, self.control_parameter))
        for sdi in self.sound_definition_instances:
            return_list += [" " + line for line in sdi.to_string()]
        for (index, envelope) in enumerate(self.envelopes):
            return_list += [" " + line for line in envelope.to_string()]
        return return_list
    
    # Emits a string list representation of the Layer as it appears in
    #  the .fdp, including all attached SoundDefInstances and Envelopes.
    # layer_name is the name that should be given to this layer in the .fdp,
    #  since this data is not saved into the .fev and must be recreated.
    # parameters is the list of Parameters from this Layer's Event,
    #  since the Layer indexs this list to determine its control parameter.
    # sounddefs is the list of SoundDefs found in the .fev containing
    #  this Layer's Event. SoundDefInstances attached to this Layer index
    #  this list.
    # Each element of the list corresponds to a line in the representation.    
    def to_xml_string(self, layer_name, parameters, sounddefs):
        return_list = []
        return_list.append("<layer>")
        return_list.append("<name>" + layer_name + "</name>")
        return_list.append("<height>100</height>")
        return_list.append("<envelope_nextid>0</envelope_nextid>")
        return_list.append("<mute>0</mute>")
        return_list.append("<solo>0</solo>")
        return_list.append("<soundlock>0</soundlock>")
        return_list.append("<envlock>0</envlock>")
        return_list.append("<priority>" + str(self.priority) + "</priority>")
        if self.control_parameter != -1:
            return_list.append("<controlparameter>" + 
                parameters[self.control_parameter].param_name + 
                "</controlparameter>")
        for sdi in self.sound_definition_instances:
            return_list += sdi.to_xml_string(sounddefs)
        for (index, envelope) in enumerate(self.envelopes):
            return_list += envelope.to_xml_string("parsed_envelope" + str(index), 
            self.envelopes, parameters)
        return_list += fev_parser_xml_const.LAYER_ENABLES.splitlines()
        return_list.append("</layer>")
        return return_list
     

# Provides functionality to adjust playback characteristics of an Event
#  in real-time during the game.
class Parameter():
    @unique
    class LoopBehavior(Enum):
        ONESHOT = 2
        ONESHOT_AND_STOP = 4
        LOOP= 8
        
        def to_xml_name(self):
            xml_name_dict = {
                self.ONESHOT: "0",
                self.ONESHOT_AND_STOP: "1",
                self.LOOP: "2"}
            return xml_name_dict[self]
    
    def __init__(self, param_name, velocity, param_min, param_max, 
     is_primary, loop_behavior, seek_speed, num_of_envelopes_controlled):
        self.param_name = param_name
        self.velocity = velocity
        self.param_min = param_min
        self.param_max = param_max
        self.is_primary = is_primary
        self.loop_behavior = loop_behavior
        self.seek_speed = seek_speed
        self.num_of_envelopes_controlled = num_of_envelopes_controlled
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse Parameter @ %#010x" % offset)
        master_offset = offset
        (param_name, master_offset) = extract_length_and_strz(content, master_offset)
        ((velocity, param_min, param_max), 
            master_offset) = extract_struct("<fff", content, master_offset)
        ((param_info,), master_offset) = extract_struct("<I", content, master_offset)
        is_primary = ((param_info & 0x01) == 0x01)
        loop_behavior = Parameter.LoopBehavior(param_info & ~0x01)
        ((seek_speed, num_of_envelopes_controlled), 
            master_offset) = extract_struct("<fI", content, master_offset)
        master_offset = consume_byte(content, master_offset, b"\x00", 4)
        return (Parameter(param_name, velocity, param_min, param_max, 
            is_primary, loop_behavior, seek_speed, 
            num_of_envelopes_controlled), master_offset)
    
    # Emits a string representation of the Property.
    def to_string(self):
        return (("Parameter[name=\'%s\', velocity=%f, min=%f, max=%f, "
            + "is_primary=%s, loop_behavior=%s, seek_speed=%f, num_controlled_envelopes=%d]") %
            (self.param_name, self.velocity, self.param_min, self.param_max,
                self.is_primary, self.loop_behavior, self.seek_speed, 
                self.num_of_envelopes_controlled))
    
    # Emits a string list representation of the Property as it appears in the .fdp.
    # The parameter ruler spacing is not needed by the event data, so it
    #  is not saved to the .fev. We set the spacing to be in 10% intervals,
    #  and it can later be changed by the user to their liking.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string(self):
        return_list = []
        return_list.append("<parameter>")
        return_list.append("<name>" + self.param_name + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list.append("<primary>" + bool_to_string(self.is_primary, "1", "0") + "</primary>")
        return_list.append("<loopmode>" + self.loop_behavior.to_xml_name() + "</loopmode>")
        return_list.append("<rangeunits></rangeunits>")
        return_list.append("<rangemin>" + str(self.param_min) + "</rangemin>")
        return_list.append("<rangemax>" + str(self.param_max) + "</rangemax>")
        # The parameter spacing isn't saved, so set it to 10% intervals.
        return_list.append("<rangespacing>" + str((self.param_max - self.param_min) / 10.0) + "</rangespacing>")
        return_list.append("<keyoffonsilence>0</keyoffonsilence>")
        return_list.append("<velocity>" + str(self.velocity) + "</velocity>")
        return_list.append("<seekspeed>" + str(self.seek_speed) + "</seekspeed>")
        return_list.append("</parameter>")
        return return_list


# The main constituent of the FMOD Sound Event system. Responsible for
#  packaging sound information that can be requested in-game. The playback
#  of events is handled by FMOD.
# Events and their folders (Event Groups) are shown in the Events view,
#  in the Event Groups pane. Each Event also belongs to an Event Category,
#  which is shown in the same view in the Event Categories pane.
class Event():
    @unique
    class EventType(Enum):
        SIMPLE = 0x10
        COMPLEX = 0x08
     
    @unique
    class EventMode(Enum):
        TWO_DIM = 0x08
        THREE_DIM = 0x10
        
        def to_xml_name(self):
            xml_name_dict = {
                self.TWO_DIM: "x_2d",
                self.THREE_DIM: "x_3d"}
            return xml_name_dict[self]
    
    @unique
    class ThreeDimRolloff(Enum):
        LOGARITHMIC = 0x0010
        LINEAR = 0x0020
        CUSTOM = 0x0400
        
        def to_xml_name(self):
            xml_name_dict = {
                self.LOGARITHMIC: "Logarithmic",
                self.LINEAR: "Linear",
                self.CUSTOM: "Custom"}
            return xml_name_dict[self]
    
    @unique
    class ThreeDimPosition(Enum):
        HEAD_RELATIVE = 0x04
        WORLD_RELATIVE = 0x08
        
        def to_xml_name(self):
            xml_name_dict = {
                self.HEAD_RELATIVE: "Head_relative",
                self.WORLD_RELATIVE: "World_relative"}
            return xml_name_dict[self]
    
    @unique    
    class PitchUnits(Enum):
        OCTAVES = 0x00
        SEMITONES = 0x40
        TONES = 0x80
        
        def to_xml_name(self):
            xml_name_dict = {
                self.OCTAVES: "Octaves",
                self.SEMITONES: "Semitones",
                self.TONES: "Tones"}
            return xml_name_dict[self]
            
        
    
    @unique
    class PlaybackBehavior(Enum):
        # Different from the one in EventCategory, for some reason.
        STEAL_OLDEST = 1
        STEAL_NEWEST = 2
        STEAL_QUIETEST = 3
        JUST_FAIL = 4
        JUST_FAIL_IF_QUIETEST = 5
        
        def to_xml_name(self):
            xml_name_dict = {
                self.STEAL_OLDEST: "Steal_oldest",
                self.STEAL_NEWEST: "Steal_newest",
                self.STEAL_QUIETEST: "Steal_quietest",
                self.JUST_FAIL: "Just_fail",
                self.JUST_FAIL_IF_QUIETEST: "Just_fail_if_quietest"}
            return xml_name_dict[self]
    
    
    def __init__(self, event_name, guid, volume, pitch, 
     pitch_rand, volume_rand, priority, max_playbacks, steal_priority,
     mode, ignore_geometry, three_dim_rolloff, three_dim_position,
     three_dim_min_dist, three_dim_max_dist, oneshot, pitch_rand_units,
     speaker_l, speaker_r, speaker_c, speaker_lfe, speaker_lr,
     speaker_rr, speaker_ls, speaker_rs, cone_inside_angle, 
     cone_outside_angle, cone_outside_volume, max_playback_behavior,
     doppler_factor, reverb_dry, reverb_wet, speaker_spread, 
     fadein_time, fadeout_time, spawn_intensity, spawn_intensity_rand,
     pan_level, position_rand, layers, parameters, user_properties,
     category_names):
        self.event_name = event_name
        self.guid = guid
        self.volume = volume
        self.pitch = pitch
        self.pitch_rand = pitch_rand
        self.volume_rand = volume_rand
        self.priority = priority
        self.max_playbacks = max_playbacks
        self.steal_priority = steal_priority
        self.mode = mode
        self.ignore_geometry = ignore_geometry
        self.three_dim_rolloff = three_dim_rolloff
        self.three_dim_position = three_dim_position
        self.three_dim_min_dist = three_dim_min_dist
        self.three_dim_max_dist = three_dim_max_dist
        self.oneshot = oneshot
        self.pitch_rand_units = pitch_rand_units
        self.speaker_l = speaker_l
        self.speaker_r = speaker_r
        self.speaker_c = speaker_c
        self.speaker_lfe = speaker_lfe
        self.speaker_lr = speaker_lr
        self.speaker_rr = speaker_rr
        self.speaker_ls = speaker_ls
        self.speaker_rs = speaker_rs
        self.cone_inside_angle = cone_inside_angle
        self.cone_outside_angle = cone_outside_angle
        self.cone_outside_volume = cone_outside_volume
        self.max_playback_behavior = max_playback_behavior
        self.doppler_factor = doppler_factor
        self.reverb_dry = reverb_dry
        self.reverb_wet = reverb_wet
        self.speaker_spread = speaker_spread
        self.fadein_time = fadein_time
        self.fadeout_time = fadeout_time
        self.spawn_intensity = spawn_intensity
        self.spawn_intensity_rand = spawn_intensity_rand
        self.pan_level = pan_level
        self.position_rand = position_rand
        self.layers = layers
        self.parameters = parameters
        self.user_properties = user_properties
        self.category_names = category_names
    
    @classmethod    
    def from_file_content(cls, content, offset):
        log.info("Parse Event @ %#010x" % offset)
        master_offset = offset 
        ((event_type_value,), master_offset) = extract_struct("<I", content, master_offset)
        event_type = Event.EventType(event_type_value)
        (event_name, master_offset) = extract_length_and_strz(content, master_offset)
        ((guid_chunk1, guid_chunk2, guid_chunk3), 
            master_offset) = extract_struct("<4s2s2s", content, master_offset)
        ((guid_chunk4, guid_chunk5), 
            master_offset) = extract_struct("<2s6s", content, master_offset)
        # Reverse the first three chunks and hexify all chunks to build the GUID string
        guid = "-".join([guid_chunk1[::-1].hex(), guid_chunk2[::-1].hex(),
            guid_chunk3[::-1].hex(), guid_chunk4.hex(), guid_chunk5.hex()])
            
        ((volume, pitch, pitch_rand, volume_rand, priority, 
            max_playbacks, steal_priority), 
            master_offset) = extract_struct("<ffffIIi", content, master_offset)
            
        ((mode_value,), master_offset) = extract_struct("<H", content, master_offset)
        mode = Event.EventMode(mode_value)
        
        ((geom_flags,), master_offset) = extract_struct("<H", content, master_offset)
        ignore_geometry = ((geom_flags & 0xf000) == 0x4000)
        three_dim_rolloff = Event.ThreeDimRolloff(geom_flags & 0x0ff0)
        three_dim_position = Event.ThreeDimPosition(geom_flags & 0x00f)
        
        ((three_dim_min_dist, three_dim_max_dist), 
            master_offset) = extract_struct("<ff", content, master_offset)
        master_offset = consume_byte(content, master_offset, b"\x00", length = 2)
        ((oneshot_value, pitch_rand_units_value), master_offset) = extract_struct("<BB", content, master_offset)
        oneshot = (oneshot_value == 0x08)
        pitch_rand_units = Event.PitchUnits(pitch_rand_units_value)
        
        ((speaker_l, speaker_r, speaker_c, speaker_lfe, speaker_lr,
            speaker_rr, speaker_ls, speaker_rs, cone_inside_angle,
            cone_outside_angle, cone_outside_volume), 
            master_offset) = extract_struct("<11f", content, master_offset)
        
        ((max_playback_behavior_value,), 
            master_offset) = extract_struct("<I", content, master_offset)
        max_playback_behavior = Event.PlaybackBehavior(max_playback_behavior_value)
        
        ((doppler_factor, reverb_dry, reverb_wet, speaker_spread,
            fadein_time, fadeout_time, spawn_intensity, 
            spawn_intensity_rand, pan_level, position_rand), 
            master_offset) = extract_struct("<4f2I3fI", content, master_offset)
        
        num_of_layers = 1
        if event_type == Event.EventType.COMPLEX:
            ((num_of_layers,), master_offset) = extract_struct("<I", content, master_offset)
        layers = []
        for _ in range(num_of_layers):
            (layer, master_offset) = Layer.from_file_content(content, master_offset, event_type=event_type)
            layers.append(layer)
        parameters = []
        user_properties = []
        if event_type == Event.EventType.COMPLEX:
            ((num_of_params,), master_offset) = extract_struct("<I", content, master_offset)
            for _ in range(num_of_params):
                (param, master_offset) = Parameter.from_file_content(content, master_offset)
                parameters.append(param)
            ((num_of_user_props,), master_offset) = extract_struct("<I", content, master_offset) 
            for _ in range(num_of_user_props):
                (user_prop, master_offset) = UserProperty.from_file_content(content, master_offset)
                user_properties.append(user_prop)
        category_names = []
        ((num_of_cats,), master_offset) = extract_struct("<I", content, master_offset)
        for _ in range(num_of_cats):
            (cat_name, master_offset) = extract_length_and_strz(content, master_offset)
            category_names.append(cat_name)
        
        return (Event(event_name, guid, volume, pitch, pitch_rand, volume_rand, 
            priority, max_playbacks, steal_priority, mode, ignore_geometry, 
            three_dim_rolloff, three_dim_position, three_dim_min_dist, 
            three_dim_max_dist, oneshot, pitch_rand_units, speaker_l, 
            speaker_r, speaker_c, speaker_lfe, speaker_lr, speaker_rr, 
            speaker_ls, speaker_rs, cone_inside_angle, cone_outside_angle, 
            cone_outside_volume, max_playback_behavior, doppler_factor, 
            reverb_dry, reverb_wet, speaker_spread, fadein_time, 
            fadeout_time, spawn_intensity, spawn_intensity_rand, 
            pan_level, position_rand, layers, parameters, user_properties, 
            category_names), master_offset)
    
    # Emits a string list representation of the Event, including all attached
    #  Layers, Parameters and User Properties.
    # Each element of the list corresponds to a line in the representation.    
    def to_string(self):
        return_list = []
        return_list.append("Event[name=\'%s\', guid=%s, ..." % (self.event_name, self.guid))
        return_list.append(" volume=%f, pitch=%f, pitch_rand=%f, volume_rand=%f, ..." %
            (self.volume, self.pitch, self.pitch_rand, self.volume_rand))
        return_list.append(" priority=%d, max_playbacks=%d, steal_priority=%d, mode=%s, ..." %
            (self.priority, self.max_playbacks, self.steal_priority, self.mode))
        return_list.append(" ignore_geometry=%s, 3d_rolloff=%s, 3d_position=%s, ..." %
            (self.ignore_geometry, self.three_dim_rolloff, self.three_dim_position))
        return_list.append(" 3d_min_dist=%f, 3d_max_dist=%f, oneshot=%s, pitch_rand_units=%s, ..." %
            (self.three_dim_min_dist, self.three_dim_max_dist, self.oneshot, self.pitch_rand_units))
        return_list.append(" speaker_l=%f, speaker_r=%f, speaker_c=%f, speaker_lfe=%f, ..." %
            (self.speaker_l, self.speaker_r, self.speaker_c, self.speaker_lfe))
        return_list.append(" speaker_lr=%f, speaker_rr=%f, speaker_ls=%f, speaker_rs=%f, ..." %
            (self.speaker_lr, self.speaker_rr, self.speaker_ls, self.speaker_rs))
        return_list.append(" cone_inside_angle=%f, cone_outside_angle=%f, cone_outside_volume=%f, ..." %
            (self.cone_inside_angle, self.cone_outside_angle, self.cone_outside_volume))
        return_list.append(" max_playback_behavior=%s, doppler_factor=%f, ..." %
            (self.max_playback_behavior, self.doppler_factor))
        return_list.append(" reverb_dry=%f, reverb_wet=%f, speaker_spread=%f, ..." %
            (self.reverb_dry, self.reverb_wet, self.speaker_spread))
        return_list.append(" fadein_time=%d, fadeout_time=%d, spawn_intensity=%f, spawn_intensity_rand=%f, ..." %
            (self.fadein_time, self.fadeout_time, self.spawn_intensity, self.spawn_intensity_rand))
        return_list.append(" pan_level=%f, position_rand=%d]" %
            (self.pan_level, self.position_rand))
        if len(self.layers) > 0:
            return_list.append("  Layers:")
            for layer in self.layers:
                return_list += ["   " + line for line in layer.to_string()]
        if len(self.parameters) > 0:
            return_list.append("  Parameters:")
            for (index, param) in enumerate(self.parameters):
                return_list.append("   [%d] %s" % (index, param.to_string()))
        if len(self.user_properties) > 0:
            return_list.append("  User Properties:")
            for (index, prop) in enumerate(self.user_properties):
                return_list.append("   [%d] %s" % (index, prop.to_string()))
        return_list.append("  Categories: %s" % str(self.category_names))
        return return_list
    
    # Emits a string list representation of the Event as it appears in the
    #  .fdp, including all attached Layers, Parameters and User Properties.
    # sounddefs is the list of SoundDefs from the .fev that this event is
    #  contained in. SoundDefInstances from Layers in this Event reference
    #  these SoundDefs.
    # Each element of the list corresponds to a line in the representation.    
    def to_xml_string(self, sounddefs):
        return_list = []
        return_list.append("<event>")
        return_list.append("<name>" + self.event_name + "</name>")
        return_list.append("<guid>{" + self.guid + "}</guid>")
        return_list.append("<parameter_nextid>0</parameter_nextid>")
        return_list.append("<layer_nextid>0</layer_nextid>")
        for (index, layer) in enumerate(self.layers):
            return_list += layer.to_xml_string("parsed_layer" + str(index), self.parameters, sounddefs)
        for param in self.parameters:
            return_list += param.to_xml_string()
        return_list += fev_parser_xml_const.EVENT_CAR.splitlines()
        return_list.append("<volume_db>" + str(field_ratio_to_decibel(self.volume)) + "</volume_db>")
        return_list.append("<pitch>" + str(self.pitch * 4.0) + "</pitch>")
        # Pitch units aren't saved, but Pitch Randomization Units are, so use those.
        return_list.append("<pitch_units>" + self.pitch_rand_units.to_xml_name() + "</pitch_units>")
        return_list.append("<pitch_randomization>" + str(self.pitch_rand * 4.0) + "</pitch_randomization>")
        return_list.append("<pitch_randomization_units>" + self.pitch_rand_units.to_xml_name() + "</pitch_randomization_units>")
        return_list.append("<volume_randomization>" + str(field_ratio_to_decibel(1-self.volume_rand))  + "</volume_randomization>")
        return_list.append("<priority>" + str(self.priority) + "</priority>")
        return_list.append("<maxplaybacks>" + str(self.max_playbacks) + "</maxplaybacks>")
        return_list.append("<maxplaybacks_behavior>" + self.max_playback_behavior.to_xml_name() + "</maxplaybacks_behavior>")
        return_list.append("<stealpriority>" + str(self.steal_priority) + "</stealpriority>")
        return_list.append("<mode>" + self.mode.to_xml_name() + "</mode>")
        return_list.append("<ignoregeometry>" + bool_to_string(self.ignore_geometry, "Yes", "No") + "</ignoregeometry>")
        return_list.append("<rolloff>" + self.three_dim_rolloff.to_xml_name() + "</rolloff>")
        return_list.append("<mindistance>" + str(self.three_dim_min_dist) + "</mindistance>")
        return_list.append("<maxdistance>" + str(self.three_dim_max_dist) + "</maxdistance>")
        return_list.append("<headrelative>" + self.three_dim_position.to_xml_name() + "</headrelative>")
        return_list.append("<oneshot>" + bool_to_string(self.oneshot, "Yes", "No") + "</oneshot>")
        return_list.append("<istemplate>No</istemplate>")
        return_list.append("<usetemplate></usetemplate>")
        return_list.append("<notes></notes>")
        for user_prop in self.user_properties:
            return_list += user_prop.to_xml_string()
        return_list.append("<category>" + self.category_names[0] + "</category>")
        return_list.append("<position_randomization>" + str(self.position_rand) + "</position_randomization>")
        return_list.append("<speaker_l>" + str(self.speaker_l) + "</speaker_l>")
        return_list.append("<speaker_c>" + str(self.speaker_c) + "</speaker_c>")
        return_list.append("<speaker_r>" + str(self.speaker_r) + "</speaker_r>")
        return_list.append("<speaker_ls>" + str(self.speaker_ls) + "</speaker_ls>")
        return_list.append("<speaker_rs>" + str(self.speaker_rs) + "</speaker_rs>")
        return_list.append("<speaker_lb>" + str(self.speaker_lr) + "</speaker_lb>")
        return_list.append("<speaker_rb>" + str(self.speaker_rr) + "</speaker_rb>")
        return_list.append("<speaker_lfe>" + str(self.speaker_lfe) + "</speaker_lfe>")
        return_list.append("<speaker_config>0</speaker_config>")
        return_list.append("<speaker_pan_r>1</speaker_pan_r>")
        return_list.append("<speaker_pan_theta>0</speaker_pan_theta>")
        return_list.append("<cone_inside_angle>" + str(self.cone_inside_angle) + "</cone_inside_angle>")
        return_list.append("<cone_outside_angle>" + str(self.cone_outside_angle) + "</cone_outside_angle>")
        return_list.append("<cone_outside_volumedb>" + 
            str(field_ratio_to_decibel(self.cone_outside_volume)) +
            "</cone_outside_volumedb>")
        return_list.append("<doppler_scale>" + str(self.doppler_factor) + "</doppler_scale>")
        return_list.append("<reverbdrylevel_db>" + str(self.reverb_dry) + "</reverbdrylevel_db>")
        return_list.append("<reverblevel_db>" + str(self.reverb_wet) + "</reverblevel_db>")
        return_list.append("<speaker_spread>" + str(self.speaker_spread) + "</speaker_spread>")
        return_list.append("<panlevel3d>" + str(self.pan_level) + "</panlevel3d>")
        return_list.append("<fadein_time>" + str(self.fadein_time) + "</fadein_time>")
        return_list.append("<fadeout_time>" + str(self.fadeout_time) + "</fadeout_time>")
        return_list.append("<spawn_intensity>" + str(self.spawn_intensity) + "</spawn_intensity>")
        return_list.append("<spawn_intensity_randomization>" + 
            str(self.spawn_intensity_rand) + 
            "</spawn_intensity_randomization>")
        return_list += fev_parser_xml_const.EVENT_TEMPLATE.splitlines()
        return_list.append("</event>")
        return return_list
        

# The folders used to organize Events for more convenient referencing in-game.
# Unlike Event Categories, which are used to organize compile-time mixing of 
#  Events, Event Groups are used to organize Events in-game.
class EventGroup():
    def __init__(self, name, user_properties, subgroups, events):
        self.name = name
        self.user_properties = user_properties
        self.subgroups = subgroups
        self.events = events
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse EventGroup @ %#010x" % offset)
        master_offset = offset
        (group_name, master_offset) = extract_length_and_strz(content, master_offset)
        ((num_of_user_properties, num_of_subgroups, num_of_events), 
            master_offset) = extract_struct("<III", content, master_offset)
        user_properties = []
        for _ in range(num_of_user_properties):
            (user_prop, master_offset) = UserProperty.from_file_content(content, master_offset)
            user_properties.append(user_prop)
        subgroups = []
        for _ in range(num_of_subgroups):
            (subgroup, master_offset) = EventGroup.from_file_content(content, master_offset)
            subgroups.append(subgroup)
        events = []
        for _ in range(num_of_events):
            (event, master_offset) = Event.from_file_content(content, master_offset)
            events.append(event)
        return (EventGroup(group_name, user_properties, subgroups, events), master_offset)
     
    # Emits a string list representation of the Event Group, including all 
    #  User Properties, sub-Event Groups, and contained Events.
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append("EventGroup[name=\'%s\']" % self.name)
        if len(self.user_properties) > 0:
            return_list.append(" User Properties:")
            for (index, prop) in enumerate(self.user_properties):
                return_list.append("  [%d] %s" % (index, prop.to_string()))
        for group in self.subgroups:
            return_list += [" " + line for line in group.to_string()]
        for event in self.events:
            return_list += [" " + line for line in event.to_string()]
        return return_list
    
    # Emits a string list representation of the Event Group as it appears
    #  in the .fdp, including all User Properties, sub-Event Groups, and
    #  contained Events.
    # sounddefs is a list of all the SoundDefs in the .fev that the EventGroup
    #  is found in. The SoundDefInstances on the Layers in the Event recursively
    #  contained in this Event Group may reference these SoundDefs.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string(self, sounddefs):
        return_list = []
        return_list.append("<eventgroup>")
        return_list.append("<name>" + self.name + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list.append("<eventgroup_nextid>0</eventgroup_nextid>")
        return_list.append("<event_nextid>0</event_nextid>")
        return_list.append("<open>0</open>")
        return_list.append("<notes></notes>")
        for user_prop in self.user_properties:
            return_list += user_prop.to_xml_string()
        for subgroup in self.subgroups:
            return_list += subgroup.to_xml_string(sounddefs)
        for event in self.events:
            return_list += event.to_xml_string(sounddefs)
        return_list.append("</eventgroup>")
        return return_list
        

# A representation of the properties that can be set about a Sound Definition
#  in the Sound Definitions view. To save space, these collections of properties
#  are saved seperate from the SoundDef itself in the .fev, so that
#  multiple SoundDefs can reference the same SoundDefProperty
class SoundDefProperty():
    @unique
    class PlayMode(Enum):
        SEQUENTIAL = 0
        RANDOM = 1
        RANDOM_NO_REPEAT = 2
        SEQUENTIAL_EVENT_RESTART = 3
        SHUFFLE = 4
        PROGRAMMER_SELECTED = 5
        SHUFFLE_GLOBAL = 6
        
        def to_xml_name(self):
            xml_name_dict = {
                self.SEQUENTIAL: "sequentialnoeventrestart",
                self.RANDOM: "random",
                self.RANDOM_NO_REPEAT: "randomnorepeat",
                self.SEQUENTIAL_EVENT_RESTART: "sequential",
                self.SHUFFLE: "shuffle",
                self.PROGRAMMER_SELECTED: "programmerselected",
                self.SHUFFLE_GLOBAL: "shuffleglobal"}
            return xml_name_dict[self]
        
    @unique
    class RecalculateRand(Enum):
        EVERY_SPAWN = 0
        ON_TRIGGER = 1
        ON_START = 2
    
    def __init__(self, play_mode, spawn_time_min, spawn_time_max, max_spawned,
     volume, volume_randmethod, volume_randmin, volume_randmax, volume_rand,
     pitch, pitch_randmethod, pitch_randmin, pitch_randmax, pitch_rand,
     recalc_pitch_rand, three_dim_position_rand):
        self.play_mode = play_mode
        self.spawn_time_min = spawn_time_min
        self.spawn_time_max = spawn_time_max
        self.max_spawned = max_spawned
        self.volume = volume
        self.volume_randmethod = volume_randmethod
        self.volume_randmin = volume_randmin
        self.volume_randmax = volume_randmax
        self.volume_rand = volume_rand
        self.pitch = pitch
        self.pitch_randmethod = pitch_randmethod
        self.pitch_randmin = pitch_randmin
        self.pitch_randmax = pitch_randmax
        self.pitch_rand = pitch_rand
        self.recalc_pitch_rand = recalc_pitch_rand
        self.three_dim_position_rand = three_dim_position_rand
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse SoundDefProperty @ %#010x" % offset)
        master_offset = offset 
        ((play_mode_value, spawn_time_min, spawn_time_max, max_spawned),
            master_offset) = extract_struct("<IIII", content, master_offset)
        play_mode = SoundDefProperty.PlayMode(play_mode_value)
        
        ((volume, volume_randmethod, volume_randmin, volume_randmax, volume_rand),
            master_offset) = extract_struct("<fIfff", content, master_offset)
        ((pitch, pitch_randmethod, pitch_randmin, pitch_randmax, pitch_rand),
            master_offset) = extract_struct("<fIfff", content, master_offset)
        ((recalc_pitch_rand_value, three_dim_position_rand), 
            master_offset) = extract_struct("<If", content, master_offset)
        recalc_pitch_rand = SoundDefProperty.RecalculateRand(recalc_pitch_rand_value)
        return (SoundDefProperty(play_mode, spawn_time_min, spawn_time_max, 
            max_spawned, volume, volume_randmethod, volume_randmin, 
            volume_randmax, volume_rand, pitch, pitch_randmethod, 
            pitch_randmin, pitch_randmax, pitch_rand, recalc_pitch_rand, 
            three_dim_position_rand), master_offset)

    # Emits a string list representation of the SoundDefProperty.
    # Each element of the list corresponds to a line in the representation.
    def to_string(self):
        return_list = []
        return_list.append("SoundDefProperty[play_mode=%s, spawn_time_min=%d, spawn_time_max=%d, max_spawned=%d, ..." %
            (self.play_mode, self.spawn_time_min, self.spawn_time_max, self.max_spawned))
        return_list.append(" volume=%f, volume_randmethod=%d, volume_randmin=%f, volume_randmax=%f, volume_rand=%f, ..." %
            (self.volume, self.volume_randmethod, self.volume_randmin, self.volume_randmax, self.volume_rand))
        return_list.append(" pitch=%f, pitch_randmethod=%d, pitch_randmin=%f, pitch_randmax=%f, pitch_rand=%f, ..." %
            (self.pitch, self.pitch_randmethod, self.pitch_randmin, self.pitch_randmax, self.pitch_rand))
        return_list.append(" recalc_pitch_rand=%s, 3d_position_rand=%f]" %
            (self.recalc_pitch_rand, self.three_dim_position_rand))
        return return_list
   
    # Emits a string list representation of the SoundDefProperty, as 
    #  a chunk of data to be inserted into the representation of a SoundDef.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string(self):
        return_list = []
        return_list.append("<type>" + self.play_mode.to_xml_name() + "</type>")
        return_list.append("<spawntime_min>%d</spawntime_min>" % self.spawn_time_min)
        return_list.append("<spawntime_max>%d</spawntime_max>" % self.spawn_time_max)
        return_list.append("<spawn_max>%d</spawn_max>" % self.max_spawned)
        return_list.append("<mode>0</mode>")
        return_list.append("<pitch>" + str(self.pitch * 4.0) + "</pitch>")
        return_list.append("<pitch_randmethod>%d</pitch_randmethod>" % self.pitch_randmethod)
        return_list.append("<pitch_random_min>" + str(self.pitch_randmin * 4.0) + "</pitch_random_min>")
        return_list.append("<pitch_random_max>" + str(self.pitch_randmax * 4.0) + "</pitch_random_max>")
        return_list.append("<pitch_randomization>" + str(self.pitch_rand * 4.0) + "</pitch_randomization>")
        return_list.append("<pitch_recalculate>%d</pitch_recalculate>" % self.recalc_pitch_rand.value)
        return_list.append("<volume_db>" + str(field_ratio_to_decibel(self.volume)) + "</volume_db>")
        return_list.append("<volume_randmethod>%d</volume_randmethod>" % self.volume_randmethod)
        return_list.append("<volume_random_min>" + str(field_ratio_to_decibel(self.volume_randmin)) + "</volume_random_min>")
        return_list.append("<volume_random_max>" + str(field_ratio_to_decibel(self.volume_randmax)) + "</volume_random_max>")
        return_list.append("<volume_randomization>" + str(field_ratio_to_decibel(self.volume_rand)) + "</volume_randomization>")
        return_list.append("<position_randomization>" + str(self.three_dim_position_rand) + "</position_randomization>")
        return return_list
   

# A container for .fev-specific information about the wavetables found
#  in a given wavebank. The audio data and specific format information
#  before and after compression is saved into the .fsb instead.
class Waveform():
    def __init__(self, weight, name, bank_name, index_in_bank, playtime):
        self.weight = weight
        self.name = name
        self.bank_name = bank_name
        self.index_in_bank = index_in_bank
        self.playtime = playtime
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse Waveform @ %#010x" % offset)
        master_offset = offset 
        master_offset = consume_byte(content, master_offset, b"\x00", 4)
        ((weight,), master_offset) = extract_struct("<I", content, master_offset)
        (name, master_offset) = extract_length_and_strz(content, master_offset)
        (bank_name, master_offset) = extract_length_and_strz(content, master_offset)
        ((index_in_bank, playtime), master_offset) = extract_struct("<II", content, master_offset)
        return (Waveform(weight, name, bank_name, index_in_bank, playtime), master_offset)
    
    # Emits a string representation of the Waveform.
    def to_string(self):
        return (("Waveform[weight=%d, name=\'%s\', bank_name=\'%s\', " + 
            "index_in_bank=%d, playtime=%d]") % (self.weight, self.name, 
            self.bank_name, self.index_in_bank, self.playtime))

    # Emits a string list representation of the Waveform.
    # Each element of the list corresponds to a line in the representation.            
    def to_xml_string(self):
        return_list = []
        return_list.append("<waveform>")
        return_list.append("<filename>" + self.name + "</filename>")
        return_list.append("<soundbankname>" + self.bank_name + "</soundbankname>")
        return_list.append("<weight>%d</weight>" % self.weight)
        return_list.append("<percentagelocked>0</percentagelocked>")
        return_list.append("</waveform>")
        return return_list
        

# An object that contains sound-producing entities (e.g. wavetables)        
class SoundDef():
    def __init__(self, name, sounddef_prop_index, waveforms):
        self.name = name
        self.sounddef_prop_index = sounddef_prop_index
        self.waveforms = waveforms
        
    @classmethod
    def from_file_content(cls, content, offset):
        log.info("Parse SoundDef @ %#010x" % offset)
        master_offset = offset 
        (name, master_offset) = extract_length_and_strz(content, master_offset)
        ((sounddef_prop_index, num_of_waveforms), 
            master_offset) = extract_struct("<II", content, master_offset)
        waveforms = []
        for _ in range(num_of_waveforms):
            (wf, master_offset) = Waveform.from_file_content(content, master_offset)
            waveforms.append(wf)
        return (SoundDef(name, sounddef_prop_index, waveforms), master_offset)
    
    # Emits a string list representation of the SoundDef.
    # Each element of the list corresponds to a line in the representation.    
    def to_string(self):
        return_list = []
        return_list.append("SoundDef[name='%s\', sounddef_prop_index=%d]" %
            (self.name, self.sounddef_prop_index))
        return_list += [" " + wf.to_string() for wf in self.waveforms]
        return return_list
    
    # Emits a string list representation of the SoundDef as it appears in
    #  the .fdp.
    # sounddef_properties_list is the list of SoundDefPropertys that
    #  are parsed from the .fev containing this SoundDef. This SoundDef
    #  indexes this list to determine its properties.
    # Each element of the list corresponds to a line in the representation.    
    def to_xml_string(self, sounddef_properties_list):
        return_list = []
        return_list.append("<sounddef>")
        return_list.append("<name>" + self.name + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list += sounddef_properties_list[self.sounddef_prop_index].to_xml_string()
        return_list.append("<notes></notes>")
        for wf in self.waveforms:
            return_list += wf.to_xml_string()
        return_list.append("</sounddef>")
        return return_list
        
# A folder object that holds SoundDefs.
# Unlike other objects, this is not saved into the .fev or .fsb. Instead
#  the folder hierarchy of SoundDefFolders and SoundDefs must be reconstructed
#  from the flattened filepaths of the SoundDefs.        
class SoundDefFolder():
    def __init__(self, name):
        self.name = name
        self.subfolders = {}
        self.sounddefs = []
    
    # Adds a SoundDef as a (possibly indirect) child of this SoundDefFolder.
    #  New sub-SoundDefFolders will be created to match path_to_sounddef, which
    #  is a Unix-style path relative to this folder. 
    #  That is, the path must either start with the path seperator '/' to signify 
    #  that the SoundDef is contained in a sub-SoundDefFolder, or must 
    #  contain no path separators at all.
    # Raises ValueError if the path does not match the specified format.
    def add_new_sounddef(self, path_to_sounddef, sounddef):
        split_path = path_to_sounddef.split('/')
        if len(split_path) == 2:
            self.sounddefs.append(sounddef)
        elif split_path[0] == '':
            folder_name = split_path.pop(1)
            subpath = '/'.join(split_path)
            if folder_name not in self.subfolders:
                self.subfolders[folder_name] = SoundDefFolder(folder_name)
            self.subfolders[folder_name].add_new_sounddef(subpath, sounddef)
        else:
            raise ValueError("Path \'" + str(path_to_sounddef) + 
                "\' is not relative to SoundDefFolder \'" + self.name + "\'.")
    
    # Emits a string list representation of the SoundDefFolder as it appears
    #  in the .fdp, recursively including all contained SoundDefFolders and SoundDefs.
    # sounddef_properties_list is the list of SoundDefPropertys parsed from
    #  the .fev that held the contained SoundDefs. SoundDefs index this
    #  list to determine their properties.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string(self, sounddef_properties_list):
        return_list = []
        return_list.append("<sounddeffolder>")
        return_list.append("<name>" + self.name + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list.append("<open>0</open>")
        for subfolder in self.subfolders:
            return_list += self.subfolders[subfolder].to_xml_string(sounddef_properties_list)
        for sounddef in self.sounddefs:
            return_list += sounddef.to_xml_string(sounddef_properties_list)
        return_list.append("</sounddeffolder>")
        return return_list
    


# The structure of the .fev file, the FMOD Event file that holds all
# event data about an FMOD project.
class FEVStruct:
    def __init__(self, version_byte, unk_offset1, unk_offset2, project_name,
     wavebanks, top_event_category, top_event_groups, sounddef_properties,
     sounddefs):
        self.version_byte = version_byte
        self.unk_offset1 = unk_offset1
        self.unk_offset2 = unk_offset2
        self.project_name = project_name
        self.wavebanks = wavebanks
        self.top_event_category = top_event_category
        self.top_event_groups = top_event_groups
        self.sounddef_properties = sounddef_properties
        self.sounddefs = sounddefs

    @classmethod
    def from_file_content(cls, content, offset=0):
        master_offset = offset
        
        # Consume magic string
        master_offset = consume_byte(content, master_offset, b"F")
        master_offset = consume_byte(content, master_offset, b"E")
        master_offset = consume_byte(content, master_offset, b"V")
        master_offset = consume_byte(content, master_offset, b"1")
        # Consume version byte (?) and unknown offsets
        ((version_byte, unk_offset1, unk_offset2), 
            master_offset) = extract_struct("<III", content, master_offset)
        # Read project name
        (project_name, master_offset) = extract_length_and_strz(content, master_offset)
        # Read wavebanks
        ((num_of_wavebanks,), master_offset) = extract_struct("<I", content, master_offset)
        wavebanks = []
        for _ in range(num_of_wavebanks):
            (wavebank, master_offset) = WavebankInfo.from_file_content(content, master_offset)
            wavebanks.append(wavebank)
        # Read event category structure (rooted at master)
        (top_event_category, master_offset) = EventCategory.from_file_content(content, master_offset)
        # Read event groups
        ((num_of_top_event_groups,), master_offset) = extract_struct("<I", content, master_offset)
        top_event_groups = []
        for _ in range(num_of_top_event_groups):
            (event_group, master_offset) = EventGroup.from_file_content(content, master_offset)
            top_event_groups.append(event_group)
        # Read sound definition properties.
        ((num_of_sounddef_props,), master_offset) = extract_struct("<I", content, master_offset)
        sounddef_properties = []
        for _ in range(num_of_sounddef_props):
            (sdp, master_offset) = SoundDefProperty.from_file_content(content, master_offset)
            sounddef_properties.append(sdp)
        # Read sound definitions.
        ((num_of_sounddefs,), master_offset) = extract_struct("<I", content, master_offset)
        sounddefs = []
        for _ in range(num_of_sounddefs):
            (sd, master_offset) = SoundDef.from_file_content(content, master_offset)
            sounddefs.append(sd)
        # Read reverb (TODO)
        master_offset = consume_byte(content, master_offset, b"\x00", 4)
        # Read music (TODO)
        ((size_of_music_block,), _) = extract_struct("<I", content, master_offset)
        master_offset += size_of_music_block
        
        return FEVStruct(version_byte, unk_offset1, unk_offset2, project_name,
            wavebanks, top_event_category, top_event_groups, sounddef_properties,
            sounddefs)
            
    # Emits a string representation of the FEV file.
    def to_string(self):
        return_list = []
        return_list.append("FEV1 v%08x" % self.version_byte)
        return_list.append("Unknown Offsets: (%#010x, %#010x)" % 
            (self.unk_offset1, self.unk_offset2))
        return_list.append("Name: %s" % self.project_name)
        return_list.append("Wavebanks:")
        for (i, wvb) in enumerate(self.wavebanks):
            return_list.append(" [%d] " % i + wvb.to_string())
        return_list.append("Event Categories:")
        return_list += [" " + line for line in self.top_event_category.to_string()]
        return_list.append("Event Groups:")
        for event_group in self.top_event_groups:
            return_list += [" " + line for line in event_group.to_string()]
        return_list.append("SoundDef Properties:")
        for (i, sdp) in enumerate(self.sounddef_properties):
            sdp_to_string = sdp.to_string()
            return_list.append(" [%02d] " % i + sdp_to_string[0])
            return_list += ["      " + line for line in sdp_to_string[1:]]
        return_list.append("Sound Definitions:")
        for (i, sd) in enumerate(self.sounddefs):
            sd_to_string = sd.to_string()
            return_list.append(" [%02d] " % i + sd_to_string[0])
            return_list += ["      " + line for line in sd_to_string[1:]]
        return "\n".join(return_list)

    # Emits a string list representation of the first chunk of the .fdp file 
    #  generated from the parsed .fev file.
    # This starting chunk should be followed by chunks generated from
    #  each of the referenced Wavebanks, found by parsing the appropriate 
    #  .fsb file.
    # The final closing chunk is generated by to_xml_string_end.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string_start(self):
        return_list = []
        return_list.append("<project>")
        return_list.append("<name>" + self.project_name + "</name>")
        return_list.append("<guid>{" + get_new_guid() + "}</guid>")
        return_list += fev_parser_xml_const.PROJECT_VERSION.splitlines()
        if len(self.wavebanks) > 0:
            return_list.append("<currentbank>" + self.wavebanks[0].bank_name + "</currentbank>")
        return_list += fev_parser_xml_const.PROJECT_LANGUAGE.splitlines()
        # Handle Event Categories. The top-level master category is not included.
        for event_category in self.top_event_category.subcategories:
            return_list += event_category.to_xml_string()
        # Handle Sounddefs
        #  Build Sounddef directory structure and populate it with the Sounddefs
        master_sounddeffolder = SoundDefFolder("master")
        for sd in self.sounddefs:
            master_sounddeffolder.add_new_sounddef(sd.name, sd)
        return_list += master_sounddeffolder.to_xml_string(self.sounddef_properties)
        # Handle Event Groups.
        for event_group in self.top_event_groups:
            return_list += event_group.to_xml_string(self.sounddefs)
        return_list += fev_parser_xml_const.DEFAULT_SOUNDBANK_PROPS.splitlines()
        return return_list

    # Emits a string list representation of the last chunk of the .fdp file 
    #  generated from the parsed .fev file.
    # See to_xml_string_end for more information.
    # Each element of the list corresponds to a line in the representation.
    def to_xml_string_end(self):
        return_list = []
        return_list += fev_parser_xml_const.PROJECT_FOOTER.splitlines()
        return_list.append("</project>")
        return return_list


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.WARN)
    if len(sys.argv) == 1:
        print("Usage: " + sys.argv[0] + " <FEV File>")
    else:
        with open(sys.argv[1], "rb") as f:
            content = f.read()
            fev_data = FEVStruct.from_file_content(content)
            print(fev_data.to_string())
