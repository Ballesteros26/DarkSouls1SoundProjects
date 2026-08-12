import fev_parser 
import fsb_parser
import os
import sys

import logging
log = logging.getLogger(__name__)

# Parses the given fev_data to find Sound Definitions that reference the
#  wavetable in wavebank bank_name at the given index in order to
#  determine the filepath of the wavetable.
# Returns a list of possible filepaths.
def find_paths_from_waveforms_with_bank_index(fev_data, bank_name, index):
    return_set = set([])
    for sounddef in fev_data.sounddefs:
        for waveform in sounddef.waveforms:
            if waveform.bank_name == bank_name and waveform.index_in_bank == index:
                return_set.add(waveform.name)
    return list(return_set)

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARN)
    if len(sys.argv) == 1:
        print("Usage: " + sys.argv[0] + " <FEV File>")
    else:
        with open(sys.argv[1], "rb") as f:
            content = f.read()
            fev_data = fev_parser.FEVStruct.from_file_content(content)
            output_list = fev_data.to_xml_string_start()
            
            (dirpath, filename) = os.path.split(sys.argv[1])
            fev_filename = os.path.splitext(filename)[0]
            
            
            for bank in fev_data.wavebanks:
                output_list += bank.to_xml_string_header()
                fsb_filepath = os.path.join(dirpath, bank.bank_name + ".fsb")
                if not os.path.exists(fsb_filepath):
                    log.warn("Cannot find required bank \'" + bank.bank_name + ".fsb\'. Skipping bank.")
                    continue
                    
                bank_format = fev_parser.WavebankInfo.BankOutputFormat.PCM
                with open(fsb_filepath, "rb") as g:
                    fsb_content = g.read()
                    fsb_data = fsb_parser.FSBStruct.from_file_content(fsb_content)
                    
                    # Determine bank format, if possible.
                    if len(fsb_data.samples) > 0:
                        sample = fsb_data.samples[0]
                        if fsb_parser.FSBSample.FSBSampleMode.FSOUND_IMAADPCM in sample.mode_flags:
                            bank_format = fev_parser.WavebankInfo.BankOutputFormat.ADPCM
                        if fsb_parser.FSBSample.FSBSampleMode.FSOUND_MPEG_LAYER2 in sample.mode_flags:
                            bank_format = fev_parser.WavebankInfo.BankOutputFormat.MP2
                        if fsb_parser.FSBSample.FSBSampleMode.FSOUND_MPEG_LAYER3 in sample.mode_flags:
                            bank_format = fev_parser.WavebankInfo.BankOutputFormat.MP3
                    
                    # If the bank was not paired with this .fev (i.e. they have different names),
                    #  then search for and parse the bank's .fev to identify paths for samples
                    #  that are unused in this .fev.
                    bank_original_fev_data = None
                    if fev_filename != bank.bank_name:
                        fsb_original_fev_filepath = os.path.join(dirpath, bank.bank_name + ".fev")
                        if not os.path.exists(fsb_original_fev_filepath):
                            log.error("Cannot find required file \'" + bank.bank_name + ".fev\' associated with matching bank.")
                        with open(fsb_original_fev_filepath, "rb") as h:
                            fsb_fev_content = h.read()
                            bank_original_fev_data = fev_parser.FEVStruct.from_file_content(fsb_fev_content)
                    
                    for (index, sample) in enumerate(fsb_data.samples):
                        paths = find_paths_from_waveforms_with_bank_index(fev_data, bank.bank_name, index)
                        if bank_original_fev_data:
                            original_fev_paths = find_paths_from_waveforms_with_bank_index(bank_original_fev_data, bank.bank_name, index)
                            if not set(paths).issubset(set(original_fev_paths)):
                                log.warn("Searching original fev sounddefs for wavebank with name \'" +
                                    bank.bank_name + "\' and index " + str(index) + " yielded " +
                                    str(original_fev_paths) + " but searching given fev sounddefs yielded " +
                                    str(paths) + " which are not compatible. Using given.")
                            else:
                                paths = original_fev_paths
                        
                        if len(paths) == 0:
                            default_path = "bank/" + bank.bank_name + "/" + sample.sample_name
                            log.warn("Could not find any sounddef referencing wavebank with name \'" +
                                bank.bank_name + "\' and index " + str(index) + ". Defaulting to \'" +
                                default_path + "\'. This may need to be manually corrected!")
                            output_list += sample.to_xml_string(default_path)
                        elif len(paths) == 1:
                            output_list += sample.to_xml_string(paths[0])
                        else:
                            log.warn("Searching sounddefs for wavebank with name \'" +
                                bank.bank_name + "\' and index " + str(index) + " yielded " +
                                str(paths) + ".")
                            suspected_paths = [path for path in paths if sample.sample_name in path]
                            if len(suspected_paths) == 1:
                                output_list += sample.to_xml_string(suspected_paths[0])
                            else:
                                log.error("Searching sounddefs for wavebank with name \'" +
                                    bank.bank_name + "\' and index " + str(index) + " yielded " +
                                    str(paths) + " which could not be reduced using suspected " +
                                    "sample name \'" + sample.sample_name + "\'.")
                output_list += bank.to_xml_string_footer(bank_format)
            output_list += fev_data.to_xml_string_end()
            print("\n".join(output_list))
            
