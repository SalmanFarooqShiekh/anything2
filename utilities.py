from pytesseract import image_to_string
from pdf2image import convert_from_path
from PyPDF2 import PdfFileWriter, PdfFileReader
from PIL import Image 
import barcode
import datetime
import glob
import time
import re
import os

physical_printer_name = r"Ecomm_Fulfillment___Inventory_Cage" # as determined from running 'lpstat -a' in the terminal

# sample wanted matches: 
# "111-4979156-8561 860"
# "112-6411059-1101064"
# "112-3331 456-7378648"
OID_LOOKS_LIKE_THIS = r"(\s*\d){3}-(\s*\d){7}-(\s*\d){7}"


def print_to_PP(path_to_file_to_print, for_real=False):
    '''
    PP means Plain Paper, the print media in Tray1 of the printer
    '''

    if for_real:
        os.system(r"lpr -P " + physical_printer_name + " -o BRInputSlot=Tray1 " + path_to_file_to_print)
    
    print("Sending print job to PP/Tray1 done: " + path_to_file_to_print, flush=True)


def print_to_LL(path_to_file_to_print, for_real=True):
    '''
    LL means Laser Labels, the print media in Tray2 of the printer
    '''

    if for_real:
        os.system(r"lpr -P " + physical_printer_name + " -o BRInputSlot=Tray2 " + path_to_file_to_print)
    
    print("Sending print job to LL/Tray2 done: " + path_to_file_to_print, flush=True)


def pdf_to_pages(path_to_pdf, output_dir):
    # Breaks the pdf at path_to_pdf into individual pdf's each of which contains one page of 
    # the source pdf, saving each one-page-pdf to output_dir. 
    #
    # Returns a dict of size=(number of pages in path_to_pdf) which contains the path to each
    # one-page-pdf. The keys are integers and values are path strings in the dict. The paths 
    # in the dict are relative to os.getcwd().
    # 
    # Example Usage: 
    # pages_of_pdf = pdf_to_pages(r"path/to/your.pdf")
    # page1_path   = pages_of_pdf[1]  # note that indexing of the dict starts from 1 to
    # page2_path   = pages_of_pdf[2]  # match with indexing of page numbers of the pdf,
    # page3_path   = pages_of_pdf[3]  # this was the reason a dict was used instead of a list
    # ...and so on
    # 
    # note: faster than pdf_to_images()


    output_dir = append_forward_slash_if_needed(output_dir)

    if not os.path.exists(output_dir):
        raise NotADirectoryError(output_dir)

    # will be populated and returned:
    paths = dict() 

    # split the pdf:
    with open(path_to_pdf, "rb") as opened_pdf:
        reader = PdfFileReader(opened_pdf)

        for i in range(reader.numPages):
            writer = PdfFileWriter()
            writer.addPage(reader.getPage(i))

            output_page_path = f"{output_dir}page_{i+1:04}.pdf"
            with open(output_page_path, "wb") as output_stream:
                writer.write(output_stream)
            
            paths[i+1] = output_page_path

    return paths


def pdf_to_images(path_to_pdf, output_dir):
    '''
    Breaks the pdf at path_to_pdf into individual images, each of which contains one page of 
    the source pdf, saving each image/page to output_dir. 
    
    Returns a dict of size=(number of pages in path_to_pdf) which contains the path to each
    one-page-image. The keys are integers and values are path strings. The paths 
    in the dict are relative to os.getcwd().
    
    Example Usage: 
    pages_of_pdf = pdf_to_pages(r"path/to/your.pdf")
    page1_path   = pages_of_pdf[1]  # note that indexing of the dict starts from 1 to
    page2_path   = pages_of_pdf[2]  # match with indexing of page numbers of the pdf,
    page3_path   = pages_of_pdf[3]  # this was the reason a dict was used instead of a list
    ...and so on
    '''
    
    print(timestamp() + ": Started converting pdf to images.\nPDF: " + path_to_pdf + "\nTO: " + output_dir, flush=True)

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


    print(timestamp() + ": Done converting pdf to images.", flush=True)

    return dict_of_paths_to_all_pages


def get_orders_info(ps_path_from_page_num, sl_path_from_page_num):
    # params:
    #   sl_path_from_page_num: a dict: page_num -> page_img_path
    #   ps_path_from_page_num: a dict: page_num -> page_img_path
    # 
    # returns:
    #   a dict: order_num -> another_dict where another_dict contains:
    #       "ps_path"         -> the path to the ps of this order 
    #       "sl_path"         -> the path to the sl of this order  
    #       "order_id"        -> the order_id of this order
    #       "tracking_number" -> the tracking number of the sl of this order
    #   
    #   order_num is a lot like page_num, it can be used to retrieve 
    #   the details about an order from the dict this function returns.
    
    print(timestamp() + ": Extracting order_IDs and tracking_numbers from files. Determining PS-SL matches.", flush=True)

    def k_from_v(src_dict, v_to_find):
        for k, v in src_dict.items():
            if v == v_to_find:
                return k

        raise ValueError()


    sl_oids_and_tnums = oids_and_tnums_from_sl_pages(sl_path_from_page_num)

    ps_oids  = oids_from_ps_pages(ps_path_from_page_num)
    sl_oids  = sl_oids_and_tnums[0]
    sl_tnums = sl_oids_and_tnums[1]
    
    # can be sl_oids.keys() too, they should be identical disregarding order. 
    # TODO: raise an exception if this is not the case^
    ps_page_nums = ps_oids.keys() 
    
    result = dict()
    for ps_page_num in ps_page_nums:
        ps_oid = ps_oids[ps_page_num]
        matching_sl_page_num = k_from_v(sl_oids, ps_oid)
        sl_tnum = sl_tnums[matching_sl_page_num]
        result[ps_page_num] = {
            "ps_path": ps_path_from_page_num[ps_page_num], 
            "sl_path": sl_path_from_page_num[matching_sl_page_num], 
            "order_id": ps_oid, 
            "tracking_number": sl_tnum
        }

    print(timestamp() + ": Done", flush=True)

    return result


def extract_oid_from_ps_img(ps_img_path):
    # extracts the order_id (oid) from the given packing_slip through OCR


    img_text = image_to_string(Image.open(ps_img_path))

    # desired sample match: "Order ID: 113-2705349-0340212"
    pattern = r"[Oo][Rr][Dd][Ee][Rr][\s]*[Ii][Dd]:[\s]*" + OID_LOOKS_LIKE_THIS
    match = re.search(pattern, img_text)
    order_id_string = img_text[ match.start() : match.end() ]
    # order_id_string = order_id_string.replace("-", "")
    order_id_string = order_id_string[-19:]
    # order_id_number = int(order_id_string)
    
    return order_id_string


def oids_from_ps_pages(ps_path_from_page_num):
    # param: ps_path_from_page_num should be a dict containing the path to images of all packing_slips with 
    # the keys being the page_number
    # 
    # returns: a dict() with a mapping from the page_number to the order_id of packing_slips.
    # note: page_numbers start at 1


    result = dict()
    for current_page_num in ps_path_from_page_num.keys():
        current_page_img_path = ps_path_from_page_num[current_page_num]
        result[current_page_num] = extract_oid_from_ps_img(current_page_img_path)

    return result


def oids_and_tnums_from_sl_pages(sl_path_from_page_num):
    # param: sl_path_from_page_num should be a dict() containing the path to images of all shipping_labels with
    # the keys being the page_number
    # 
    # returns: a tuple of 2 dicts: 
    # 1st one is a dict() with a mapping from the page_number to the order_id of shipping_labels.
    # 2nd one is a dict() with a mapping from the page_number to the tracking_number of shipping_labels.
    # note: page_numbers start at 1

    all_pages = all_pages_text(sl_path_from_page_num)
    oid_pages = extract_oid_pages_text_from_sl_pages(all_pages)
    oids  = extract_oids_from_sl_oid_pages(oid_pages)
    
    # remove all the "orderID page"s:
    total_page_count = len(sl_path_from_page_num)
    for i in range(len(oid_pages)):
        sl_path_from_page_num.pop(total_page_count - i)
        all_pages.pop()

    result1 = dict()
    result2 = dict()
    for page_num in sl_path_from_page_num.keys():
        corresponding_list_index = page_num - 1
        current_page_text = all_pages[corresponding_list_index]
        result1[page_num] = oids[corresponding_list_index]
        result2[page_num] = extract_tnum_from_sl_text(current_page_text)

    return result1, result2


def extract_tnum_from_sl_text(sl_page_text):
    # sample intended match: "TRK# 3933 7813 1941"
    match1 = re.search(pattern=r"TRK.{1,4}[\d]{4}[\s]{0,2}[\d]{4}[\s]{0,2}[\d]{4}", string=sl_page_text)
    
    # sample intended match: "TRACKING #: 1Z O9A Y33 03 9278 4049"
    # sample intended match: "TRACKING #: 1Z 09A Y33 03 9278 4049", notice that the OCR can mistakenly recognize 0 as O and vice versa
    match2 = re.search(pattern=r"TRACKING[\s]{0,2}#:[\s]{0,2}[\w]{2}[\s]{0,2}[\w]{3}[\s]{0,2}[\w]{3}[\s]{0,2}[\w]{2}[\s]{0,2}[\d]{4}[\s]{0,2}[\d]{4}", string=sl_page_text)

    # sample intended match: "USPS TRACKING # EP\n\n9305 5201 1140 4895 5861 69"
    # sample intended match: "USPS TRACKING # EP\n\nil il\n\n9305 5201 1140 4895 5861 69"
    match3 = re.search(pattern=r"USPS[\s]{0,2}TRACKING[\s]{0,2}#.*(\s*\d){22}", string=sl_page_text, flags=re.S)
    
    if match1:
        tnum_string = sl_page_text[ match1.start() : match1.end() ]
        tnum_string = "".join(re.split(r"\s+", tnum_string)) # removes all whitespace matched by \s
        tnum_string = tnum_string[-12:]
        return tnum_string
    elif match2:
        tnum_string = sl_page_text[ match2.start() : match2.end() ]
        tnum_string = "".join(re.split(r"\s+", tnum_string)) # removes all whitespace matched by \s
        tnum_string = tnum_string[-18:]
        tnum_string = tnum_string.replace("1ZO9A", "1Z09A")
        return tnum_string
    elif match3:
        tnum_string = sl_page_text[ match3.start() : match3.end() ]
        m = re.search(pattern=r"(\s*\d){22}", string=tnum_string)
        tnum_string = tnum_string[ m.start() : m.end() ] 
        tnum_string = "".join(re.split(r"\s+", tnum_string)) # removes all whitespace matched by \s
        return tnum_string
        
    
    raise Exception("Couldn't extract the tracking number from the following shipping label: \
                    \n--------------------\n" + sl_page_text + "\n--------------------\n")
    

def extract_oid_pages_text_from_sl_pages(all_pages_text):
    # params: all_pages_text: a list of page_text of each page sorted on page_num
    # 
    # returns: returns a list whose each item is the text of an "orderID page". 
    # The order of items in this list is the order in which they appear in all_pages_text
    # 
    # An "orderID page" is a page at the end of the Shipping Labels PDF which tells us 
    # which sl has what orderID. There can be more than one of them.


    def is_oid_page_text(page_text):
        return re.search(pattern=OID_LOOKS_LIKE_THIS, string=page_text) != None
    
    result = list()
    for page_text in all_pages_text:
        if is_oid_page_text(page_text):
            result.append(page_text)

    return result


def all_pages_text(path_from_page_num):
    # param: sl_path_from_page_num should be a dict() containing (the path to images of all shipping_labels)
    # as values with the keys being page_numbers
    # 
    # returns: a list of page_text of each page sorted on page_num

    sorted_page_nums = sorted(path_from_page_num.keys())

    result = list()
    for pnum in sorted_page_nums:
        img_text = str_from_img(path_from_page_num[pnum])
        result.append(img_text)

    return result


def extract_oids_from_sl_oid_pages(oid_page_text_list):
    # params: oid_page_text_list: a list in which each item is the text of an "orderID page"
    # 
    # returns: extracts the "orderID"s from all the text in the oid_page_text_list 
    # and returns a list of "orderID" ints


    result = list()
    for oid_page_text in oid_page_text_list:
        for match in re.finditer(pattern=OID_LOOKS_LIKE_THIS, string=oid_page_text):
            oid_str = oid_page_text[ match.start() : match.end() ]
            # oid_str = oid_str.replace("-", "")
            oid_str = oid_str.replace(" ", "")
            result.append(oid_str)

    return result


def empty_dir(dir_path):
    # deletes all contents of the given directory


    dir_path = append_forward_slash_if_needed(dir_path)
    files = glob.glob(dir_path + "*")
    for file in files:
        os.remove(file)


def str_from_img(img_path):
    return image_to_string(Image.open(img_path))


def display_alert(msg, blocking):
    # it will be a little better if this is passed rstrings


    os.system(r'osascript -e "display alert \"' + msg + r'\""' + ('' if blocking else ' &'))


def timestamp():
    # returns a timestamp of the current local time as a string


    return datetime.datetime.now().strftime("%d.%b %Y, %H:%M:%S")


def append_forward_slash_if_needed(dir_path):
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


def paste(
back, 
front1, 
front2, 
front1_pos=(0, 0), 
front2_pos=(0, 0), 
scale_front1_size=1,
scale_front2_size=1, 
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


def paste_barcodes_on_ps(oid, tnum, on, result=None):
    '''
    oid          : the  oid from which to generate the upper-right barcode 
    tnum         : the tnum from which to generate the   bottom    barcode 
    on           : the path to the image on which the generated barcode will be pasted
    result       : the path to the new image, if None the source image will be overwritten
    '''

    print(timestamp() + ": Pasting barcodes for oid: " + str(oid) + " and tnum: " + str(tnum) + " on: " + str(on), flush=True)

    oid_pos  = (1050,40)
    oid_scale_by = 1
    
    tnum_pos = (560,1680)
    tnum_scale_by = 1.8

    b1 = barcode.get("code128", oid, writer=barcode.writer.ImageWriter())
    oid_barcode = b1.save("1_a_uniquely_named_temp_file_which_won't_conflit_with_anything_else_FDAKJHFIUHIBCHEFDACN")
    
    b2 = barcode.get("code128", tnum, writer=barcode.writer.ImageWriter())
    tnum_barcode = b2.save("2_a_uniquely_named_temp_file_which_won't_conflit_with_anything_else_FDAKJHFIUHIBCHEFDACN")

    paste(
        back=on,
        front1=oid_barcode,
        front2=tnum_barcode,
        front1_pos=oid_pos, 
        front2_pos=tnum_pos, 
        scale_front1_size=oid_scale_by,
        scale_front2_size=tnum_scale_by, 
        result_path=(on if result == None else result)
    )

    os.remove(oid_barcode)
    os.remove(tnum_barcode)

    print(timestamp() + ": Done", flush=True)

def empty_or_make_new(dir_path):
    '''
    creates a new at dir_path if it doesn't exist, empties it otherwise, you 
    get a clean empty dir at dir_path either way
    '''

    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        empty_dir(dir_path)
        print(timestamp() + ": Emptied dir at: " + dir_path, flush=True)
    else:
        os.mkdir(dir_path)
        print(timestamp() + ": Made dir at: " + dir_path, flush=True)


def combine_ps_and_sl(ps_path, sl_path, output):
    '''
    There will be a new image at the path `output` which has the image at `ps_path` on the 
    left half of it and the image at `sl_path` on the right half of it
    '''
    
    print(timestamp() + ": Making a single page \nfrom: " + ps_path + " \nand: " + sl_path + " \nat: " + output, flush=True)

    IMG2_HORIZONTAL_OFFSET = 50
    
    ps = Image.open(ps_path) # 1700 x 2200
    sl = Image.open(sl_path) #  800 x 1200

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

    print(timestamp() + ": Done", flush=True)