from pytesseract import image_to_string
from pdf2image import convert_from_path
from PyPDF2 import PdfFileWriter, PdfFileReader
from PIL import Image 
import datetime
import barcode
import random
import glob
import time
import re
import os

###############################################################################################
#################################### Script Options ###########################################
###############################################################################################
PRINT_TO_PHYSICAL_PRINTER           = True
PRINT_TO_VIRTUAL_PRINTER            = False
PHYSICAL_PRINTER_NAME               = "Ecomm_Fulfillment___Inventory_Cage" # as determined from running 'lpstat -a' in the terminal
VIRTUAL_PRINTER_NAME                = "q"
SPLIT_PS_PDF_TARGET                 = os.getcwd() + os.sep + "split_ps_pdf_target/"
SPLIT_SL_PDF_TARGET                 = os.getcwd() + os.sep + "split_sl_pdf_target/"
COMBINED_IMGS_TARGET                = os.getcwd() + os.sep + "combined_pages/"
###############################################################################################
###############################################################################################
###############################################################################################


###############################################################################################
###############################################################################################
###############################################################################################
# sample wanted matches: 
# "111-4979156-8561 860"
# "112-6411059-1101064"
# "112-3331 456-7378648"
OID_LOOKS_LIKE_THIS = r"(\s*\d){3}-(\s*\d){7}-(\s*\d){7}"
PS_PAGES_MATCH_THIS = r"[Oo][Rr][Dd][Ee][Rr][\s]*[Ii][Dd]:[\s]*" + OID_LOOKS_LIKE_THIS

PS_IMG_W, PS_IMG_H = 1700, 2200 # change them if you set something other than the default dpi for PS imgs
###############################################################################################
###############################################################################################
###############################################################################################

def do_amazon_print_job(pdfA, pdfB):
    log("Proccessing: \n\t>>> '" + pdfA + "' \nand \n\t>>> '" + pdfB + "'") 
    time.sleep(3)

    empty_or_make_new(SPLIT_PS_PDF_TARGET)
    empty_or_make_new(SPLIT_SL_PDF_TARGET)
    empty_or_make_new(COMBINED_IMGS_TARGET)

    pdfA_path_from_page_num = pdf_to_images2(pdfA, SPLIT_PS_PDF_TARGET)
    pdfB_path_from_page_num = pdf_to_images2(pdfB, SPLIT_SL_PDF_TARGET)

    first_page_of_pdfA = pdfA_path_from_page_num[1]
    if is_ps_page(first_page_of_pdfA):
        ps_path_from_page_num = pdfA_path_from_page_num
        sl_path_from_page_num = pdfB_path_from_page_num
    else:
        ps_path_from_page_num = pdfB_path_from_page_num
        sl_path_from_page_num = pdfA_path_from_page_num

    sl_pdf_path = pdfB if sl_path_from_page_num == pdfB_path_from_page_num else pdfA
    orders_info = get_orders_info(ps_path_from_page_num, sl_path_from_page_num, sl_pdf_path)
    
    for order in orders_info.values():
        paste_barcodes_on_ps(order["order_id"], order["tracking_number"], order["ps_path"])

    for order in orders_info.values():
        combined_ps_and_sl_path = append_slash_if_needed(COMBINED_IMGS_TARGET) + order["order_id"] + ".png"
        combine_ps_and_sl(order["ps_path"], order["sl_path"], combined_ps_and_sl_path)
        order["combined_ps_and_sl_path"] = combined_ps_and_sl_path

    for page_num in sorted(orders_info.keys()):
        order = orders_info[page_num]
        print_to_LL(order["combined_ps_and_sl_path"], for_real=PRINT_TO_PHYSICAL_PRINTER)
        print_to_PP(order["ps_path"], for_real=PRINT_TO_PHYSICAL_PRINTER)

def get_orders_info(ps_path_from_page_num, sl_path_from_page_num, sl_pdf_path):
    sl_oids  = oids_from_sl(sl_pdf_path)
    ps_oids  = oids_from_ps(ps_path_from_page_num)
    sl_tnos  = tnos_from_sl(sl_path_from_page_num)
    
    # can be sl_oids.keys() too, they should be identical disregarding order, the spec says so 
    # TODO: raise a sensible exception if this is not the case^
    ps_page_nums = ps_oids.keys() 
    
    result = dict()
    for ps_page_num in sorted(ps_page_nums):
        ps_oid = ps_oids[ps_page_num]
        matching_sl_page_num = k_from_v(sl_oids, ps_oid)
        sl_tno = sl_tnos[matching_sl_page_num]
        result[ps_page_num] = {
            "ps_path": ps_path_from_page_num[ps_page_num], 
            "sl_path": sl_path_from_page_num[matching_sl_page_num], 
            "order_id": ps_oid, 
            "tracking_number": sl_tno
        }
        msg = "PS-SL matches " + str(ps_page_num) + " details:" \
            + "\n        ps_path: " + os.path.basename(result[ps_page_num]["ps_path"]) \
            + "\n        sl_path: " + os.path.basename(result[ps_page_num]["sl_path"]) \
            + "\n       order_id: " + result[ps_page_num]["order_id"] \
            + "\ntracking_number: " + result[ps_page_num]["tracking_number"]
        log(msg)

    return result

def pdf_to_images2(path_to_pdf, output_dir, dpi=200, range=None):
    log("Started converting pdf to images.\n\t>>> Source PDF: " + path_to_pdf + "\n\t>>> Desti. dir: " + output_dir)

    file_name = str(random.randint(1, 9999999999999999999999))
    
    output_dir = append_slash_if_needed(output_dir)
    r = " -f " + str(range[0]) + " -l " + str(range[1]) + " " if bool(range) else " "
    command = "pdftoppm" + r + "-r " + str(dpi) + " -png " + path_to_pdf + " " + output_dir + file_name  #consult man pages for pdftoppm for help
    os.system(command)
    

    dict_of_paths_to_all_pages = dict() 
    for f in sorted(glob.glob(output_dir + file_name + "*")): 
        match = re.search(r"-\d+\.png$", f)

        if match:
            matched_string = f[ match.start() : match.end() ]
            
            m = re.search(r"\d+", matched_string)
            page_num = int(matched_string[ m.start() : m.end() ])
            
            dict_of_paths_to_all_pages[page_num] = f

    log("Done converting pdf to images.")

    return dict_of_paths_to_all_pages

#########################################################################################
############################## PS RELATED FUNCTIONS #####################################
#########################################################################################

def oids_from_ps(path_from_page_num):
    result = dict()
    for pnum, path in path_from_page_num.items():
        img_text = image_to_string(Image.open(path))
        m = re.search(PS_PAGES_MATCH_THIS, img_text)
        order_id_string = img_text[ m.start() : m.end() ]
        order_id_string = order_id_string[-19:]
        result[pnum] = order_id_string
        
        log("Extracted an order_ID from a  PS: " + order_id_string)

    return result

#########################################################################################
############################## PS RELATED FUNCTIONS END #################################
#########################################################################################

# <-----------------------------------------------------------------------------------> #

#########################################################################################
############################## SL RELATED FUNCTIONS #####################################
#########################################################################################

def oids_from_sl(sl_pdf_path):
    def extr_oids_from_oid_pages(oid_pages_paths_list):
        oid_pages_text_list = list()
        for page_path in oid_pages_paths_list:
            oid_pages_text_list.append(str_from_img(page_path))
        
        oid_pages_text = "\n".join(oid_pages_text_list)
        oid_pages_lines = [line for line in oid_pages_text.split('\n') if line.strip() != ''] #removes blank lines
        oid_pages_lines.pop(0) #first line is always something we don't need
        raw_oids = oid_pages_lines

        result = dict()
        p = r"(\s*/*\d\s*){2,4}-(\s*/*\d\s*){6,8}-(\s*/*\d\s*){6,8}" #just don't touch it
        for i in range(len(raw_oids)):
            pnum = i + 1
            raw_oid_text = raw_oids[i]
            
            match = re.search(pattern=p, string=raw_oid_text)
            if bool(match):
                oid_str = raw_oid_text[ match.start() : match.end() ]
                oid_str = oid_str.replace(" ", "")
                oid_str = oid_str.replace("/", "")
                result[pnum] = oid_str
            else:
                result[pnum] = raw_oid_text
            
            log("Extracted an order_ID from an SL: " + oid_str)
        
        return result


    WORKING_DIR = "temp3310123blahblahblahblehblehbleh/" # slash at end is important
    
    os.system("rm -r " + WORKING_DIR)
    os.mkdir(WORKING_DIR)
    
    sl_path_from_page_num = pdf_to_images2(sl_pdf_path, WORKING_DIR, dpi=150)
    total_pages_count     = len(sl_path_from_page_num)
    reverse_paths         = [ sl_path_from_page_num[p] for p in sorted(sl_path_from_page_num.keys(), reverse=True) ]
    

    oid_pages_count = 0
    for path in reverse_paths:
        last_page_text = str_from_img(path)
        if is_oid_page_text(last_page_text):
            oid_pages_count += 1
        else:
            break
        
    dpi_list = list()
    for dpi in range(150, 601, 50):
        dpi_dir = WORKING_DIR + str(dpi) + "/"
        os.mkdir(dpi_dir)
        
        oid_page_num_range = (total_pages_count - oid_pages_count + 1), total_pages_count
        d = pdf_to_images2(sl_pdf_path, dpi_dir, dpi=dpi, range=oid_page_num_range)
        
        dpi_list.append(list(d.values()))

    
    dpi_list2 = list()
    for oid_pages in dpi_list:
        dpi_list2.append(extr_oids_from_oid_pages(oid_pages))

    
    page_to_frequencies = dict()
    for p in range(1, total_pages_count - oid_pages_count + 1):
        frequencies = dict()
        for d in dpi_list2:
            recognized = d[p]
            if recognized in frequencies.keys():
                frequencies[recognized] += 1
            else:
                frequencies[recognized] = 1

        page_to_frequencies[p] = frequencies 
    

    result = dict()
    for p in range(1, total_pages_count - oid_pages_count + 1):
        frequencies = page_to_frequencies[p]
        most_frequent_oid = k_from_v(frequencies, max(frequencies.values()))
        result[p] = str(most_frequent_oid)

    # for k, v in result.items():
    #     print(k, "->", v)


    os.system("rm -r " + WORKING_DIR)

    return result
    

def tnos_from_sl(sl_path_from_page_num):
    def extr_tno_from_sl(sl_page_text):
        # sample intended match: "TRK# 3933 7813 1941"
        match1 = re.search(pattern=r"TRK.{1,4}[\d]{4}[\s]{0,2}[\d]{4}[\s]{0,2}[\d]{4}", string=sl_page_text)
        
        # sample intended match: "TRACKING #: 1Z O9A Y33 03 9278 4049"
        # sample intended match: "TRACKING #: 1Z 09A Y33 03 9278 4049", notice that the OCR can mistakenly recognize 0 as O and vice versa
        match2 = re.search(pattern=r"TRACKING[\s]{0,2}#:[\s]{0,2}[\w]{2}[\s]{0,2}[\w]{3}[\s]{0,2}[\w]{3}[\s]{0,2}[\w]{2}[\s]{0,2}[\d]{4}[\s]{0,2}[\d]{4}", string=sl_page_text)

        # sample intended match: "USPS TRACKING # EP\n\n9305 5201 1140 4895 5861 69"
        # sample intended match: "USPS TRACKING # EP\n\nil il\n\n9305 5201 1140 4895 5861 69"
        match3 = re.search(pattern=r"USPS[\s]{0,2}TRACKING[\s]{0,2}#.*(\s*\d){22}", string=sl_page_text, flags=re.S)
        
        if match1:
            tno = sl_page_text[ match1.start() : match1.end() ]
            tno = "".join(re.split(r"\s+", tno)) # removes all whitespace matched by \s
            tno = tno[-12:]
        elif match2:
            tno = sl_page_text[ match2.start() : match2.end() ]
            tno = "".join(re.split(r"\s+", tno))
            tno = tno[-18:]
            tno = tno.replace("1ZO9A", "1Z09A")
        elif match3:
            tno = sl_page_text[ match3.start() : match3.end() ]
            m = re.search(pattern=r"(\s*\d){22}", string=tno)
            tno = tno[ m.start() : m.end() ] 
            tno = "".join(re.split(r"\s+", tno))
            
        
        log("Extracted a  tno      from an SL: " + tno)
        return tno    
        
        raise Exception("Couldn't extract the tracking number from the following shipping label: \
                        \n--------------------\n" + sl_page_text + "\n--------------------\n")

    result = dict()
    for pno, thetext in all_pages_text(sl_path_from_page_num).items():
        if not is_oid_page_text(thetext):
            result[pno] = extr_tno_from_sl(thetext)

    return result
    


#########################################################################################
############################## SL RELATED FUNCTIONS END #################################
#########################################################################################

# <-----------------------------------------------------------------------------------> #
















######################################################################################################################
######################################################################################################################
################################ Function likely to not not throw errors #############################################
######################################################################################################################
######################################################################################################################


def is_oid_page_text(page_text):
    return re.search(pattern=OID_LOOKS_LIKE_THIS, string=page_text) != None

def is_ps_page(a_page):
    img_text = str_from_img(a_page)
    match = re.search(PS_PAGES_MATCH_THIS, img_text)

    return bool(match)

def empty_dir(dir_path, *whitelist):
    log("Emptiying dir at: " + dir_path + ( "\nexcept: " + ", ".join(whitelist) if len(whitelist) else "" ))

    dir_path = append_slash_if_needed(dir_path)
    files = glob.glob(dir_path + "*")
    
    for i in whitelist:
        files.remove(i)
        
    for file in files:
        os.remove(file)

def str_from_img(img_path):
    return image_to_string(Image.open(img_path))

def display_alert(msg, blocking):
    # it will be a little better if this is passed rstrings


    os.system(r'osascript -e "display alert \"' + msg + r'\""' + ('' if blocking else ' &'))

def timestamp():
    # returns a timestamp of the current local time as a string

    return datetime.datetime.now().strftime("%dth, %H:%M:%S")

def append_slash_if_needed(dir_path):
    # add a forward slash at the end of a path string if it isn't already there.


    if dir_path[-1] == "/":
        append = "" 
    else:
        append = "/"
    
    return dir_path + append

def dir_len(dir_path):
    # return the number of non-hidden files in the given directory


    all_items = os.listdir(dir_path)
    non_hidden_items = list(filter((lambda item_name: item_name[0] != "."), all_items))
    return len(non_hidden_items)

def paste( back, 
front1, front2, 
front1_pos, front2_pos,
scale_front1_size, scale_front2_size, 
result_path=None
):
    '''
    Paste an image on top of another image at the required position with a scaling factor.

    back: path to an image
    front: path to an image which will be pasted on top of back
    front_pos: position of upper-left corner of front on back
    scale_front_size: scaling factor for front
    result_path: path for new file, if None then back will be overwritten
    '''

    b  = Image.open(back)
    f1 = Image.open(front1)
    f2 = Image.open(front2)

    front1_size = (
        int(f1.size[0] * scale_front1_size), 
        int(f1.size[1] * scale_front1_size)
    )
    front2_size = (
        int(f2.size[0] * scale_front2_size), 
        int(f2.size[1] * scale_front2_size)
    )

    
    f1 = f1.resize(front1_size)
    f2 = f2.resize(front2_size)

    b.paste(f1, front1_pos)
    b.paste(f2, front2_pos)

    if result_path == None:
        b.save(back, "PNG")
    else:
        b.save(result_path, "PNG")

    b.close()
    f1.close()
    f2.close()


def paste_barcodes_on_ps(oid, tno, on, result=None):
    '''
    oid          : the oid from which to generate the upper-right barcode 
    tno          : the tno from which to generate the   bottom    barcode 
    on           : the path to the image on which the generated barcode will be pasted
    result       : the path to the new image, if None the source image will be overwritten
    '''

    log("Pasting barcodes for oid: " + str(oid) + " and tno: " + str(tno) + " on: " + os.path.basename(on))

    oid_pos  = (
        int(0.61 * PS_IMG_W),
        int(0.01 * PS_IMG_H)
    )
    oid_scale_by = 1
    
    tno_pos = (
        int(0.33 * PS_IMG_W),
        int(0.76 * PS_IMG_H)
    )
    tno_scale_by = 1.8

    b1 = barcode.get("code128", oid, writer=barcode.writer.ImageWriter())
    oid_barcode = b1.save("1_a_uniquely_named_temp_file_which_won't_conflit_with_anything_else_FDAKJHFIUHIBCHEFDACN")
    
    b2 = barcode.get("code128", tno, writer=barcode.writer.ImageWriter())
    tno_barcode = b2.save("2_a_uniquely_named_temp_file_which_won't_conflit_with_anything_else_FDAKJHFIUHIBCHEFDACN")

    paste(
        back=on,
        front1=oid_barcode,
        front2=tno_barcode,
        front1_pos=oid_pos, 
        front2_pos=tno_pos, 
        scale_front1_size=oid_scale_by,
        scale_front2_size=tno_scale_by, 
        result_path=(on if result == None else result)
    )

    os.remove(oid_barcode)
    os.remove(tno_barcode)

    log("Done")

def empty_or_make_new(dir_path):
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        empty_dir(dir_path)
    else:
        os.mkdir(dir_path)
        log("Made dir at: " + dir_path)

def combine_ps_and_sl(ps_path, sl_path, output):
    '''
    There will be a new image at the path `output` which has the image at `ps_path` on the 
    left half of it and the image at `sl_path` on the right half of it
    '''
    
    log(
        "Making a single page \n\tfrom: " \
        + os.path.basename(ps_path) \
        + "\n\t and: " + os.path.basename(sl_path) \
        + "\n\t  at: " + os.path.basename(output)
    )

    IMG2_HORIZONTAL_OFFSET = 50
    
    ps = Image.open(ps_path)
    sl = Image.open(sl_path)

    # make height of sl equal to the height of ps while sl maintains its original aspect ratio
    scaling_needed = ps.height / sl.height 
    new_sl_size = int(sl.width*scaling_needed), int(sl.height*scaling_needed)
    sl = sl.resize(new_sl_size)

    canvas = Image.new("RGB", (2*ps.width, ps.height), (255, 255, 255) )
    canvas.paste(ps, (0,0))
    canvas.paste(sl, (ps.width+IMG2_HORIZONTAL_OFFSET,0) )
    canvas = canvas.transpose(Image.ROTATE_90)

    canvas.save(output, "PNG")

    ps.close()
    sl.close()
    canvas.close()

    log("Done")

def print_to_PP(path_to_file_to_print, for_real=False):
    if for_real:
        os.system(r"lpr -P " + PHYSICAL_PRINTER_NAME + " -o BRInputSlot=Tray1 " + path_to_file_to_print)
    
    if PRINT_TO_VIRTUAL_PRINTER:
        os.system(r"lpr -P " + VIRTUAL_PRINTER_NAME + " " + path_to_file_to_print)
    
    log("Sending print job to PP/Tray1 done: " + os.path.basename(path_to_file_to_print))

def print_to_LL(path_to_file_to_print, for_real=True):
    if for_real:
        os.system(r"lpr -P " + PHYSICAL_PRINTER_NAME + " -o BRInputSlot=Tray2 " + path_to_file_to_print)
    
    if PRINT_TO_VIRTUAL_PRINTER:
        os.system(r"lpr -P " + VIRTUAL_PRINTER_NAME + " " + path_to_file_to_print)
    
    log("Sending print job to LL/Tray2 done: " + os.path.basename(path_to_file_to_print))

def pdf_to_images(path_to_pdf, output_dir):
    '''
    Breaks the pdf at path_to_pdf into individual images, each of which contains one page of 
    the source pdf, saving each image/page to output_dir. 
    
    Returns a dict of size=(number of pages in path_to_pdf) which contains the path to each
    one-page-image. The keys are integers and values are path strings. The paths 
    in the dict are relative to os.getcwd().
    
    Example Usage: 
    pages_of_pdf = pdf_to_images(r"path/to/your.pdf")
    page1_path   = pages_of_pdf[1]  # note that indexing of the dict starts from 1 to
    page2_path   = pages_of_pdf[2]  # match with indexing of page numbers of the pdf,
    page3_path   = pages_of_pdf[3]  # this was the reason a dict was used instead of a list
    ...and so on
    '''
    
    log("Started converting pdf to images.\n>>> Source PDF: " + path_to_pdf + "\n>>> Dest. dir: " + output_dir)

    list_of_paths_to_all_pages = convert_from_path(
        pdf_path=path_to_pdf, 
        dpi=200, 
        output_folder=output_dir, 
        output_file=os.path.basename(path_to_pdf),
        fmt="png", 
        thread_count=8,
        paths_only=True
    )

    dict_of_paths_to_all_pages = dict() 

    for i in range(len(list_of_paths_to_all_pages)):
        dict_of_paths_to_all_pages[i+1] = list_of_paths_to_all_pages[i]


    log("Done converting pdf to images.\n")

    return dict_of_paths_to_all_pages

def all_pages_text(path_from_page_num):
    result = dict()
    for pnum, path in path_from_page_num.items():
        result[pnum] = str_from_img(path)
    return result

def k_from_v(src_dict, v_to_find):
    for k, v in src_dict.items():
        if v == v_to_find:
            return k

    raise ValueError("could not find the given value: " + str(v_to_find) + " in the given dict: " + str(src_dict))

def log(msg):
    print(timestamp() + ": " + msg, flush=True)

######################################################################################################################
######################################################################################################################
############################## Function likely to not not throw errors END ###########################################
######################################################################################################################
######################################################################################################################
