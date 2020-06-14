# lpr -P a resources/amazon/1ps.pdf;  lpr -P a resources/amazon/1sl.pdf

import utilities as u
import datetime
import time
import glob
import sys
import os
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# u.display_alert("amazon system started", blocking=False)

# Purpose of this script: It is meant to be run in the background and it will be watching a folder for 2
# PDF's: the Packing Slips PDF (ps_pdf) and the Shipping Lables PDF (sl_pdf). When the 2 PDF's pop up 
# in that folder, they will be processed and then forwarded to the physical printer.
# The folder being watched is where the Amazon Virtual Printer (i.e. VipRiser) will be saving the documents.

# First send the ps_pdf, and then you can send the sl_pdf under WAIT_TIME_FOR_2ND_PDF seconds, otherwise 
# the ps_pdf will be discarded and you will need to send the ps_pdf again before sending the sl_pdf.

# Unless otherwise mentioned, VP refers to a "Virtual Printer" in this file

###############################################################################################
# Script Options:

USE_LOG_FILE                        = False # if False, print log to the the stdout which is the terminal usually
LOG_FILE_PATH                       = os.getcwd() + os.sep + __file__ + ".log"
AMAZON_VP_DESTINATION_FOLDER        = os.getcwd() + os.sep + "amazon_virtual_printer_target/"  # '/' at the end is important
WAIT_TIME_FOR_2ND_PDF               = 180 # in seconds
###############################################################################################


if USE_LOG_FILE:
    sys.stdout = open(LOG_FILE_PATH, "at")



class AmazonWatcher:
    def __init__(self):
        self.observer = Observer()

    def start(self):
        if os.path.exists(AMAZON_VP_DESTINATION_FOLDER) and os.path.isdir(AMAZON_VP_DESTINATION_FOLDER):
            u.empty_dir(AMAZON_VP_DESTINATION_FOLDER)
        else:
            os.mkdir(AMAZON_VP_DESTINATION_FOLDER)
            msg = "Set the folder where the amazon_system's Virtual Printer is saving the PDFs to: '" + AMAZON_VP_DESTINATION_FOLDER + "'"
            u.display_alert(msg, blocking=True)
            

        self.observer.schedule(AmazonPDFHandler(), AMAZON_VP_DESTINATION_FOLDER)
        self.observer.start()
        print("\n" + u.timestamp() + ": Ready to receive a new amazon pdf-pair...\n", flush=True)

        # The observer will keep observing in its own thread.
        # We are artificially keepthing this main thread alive 
        # because if it finishes execution, python will kill all 
        # its child threads too, which includes the observer threads.
        # We just want this main thread to be alive through any means.
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            print(u.timestamp() + ": Closing all threads, please wait...", flush=True)
            self.observer.stop()
            self.observer.join()
            print(u.timestamp() + ": Done", flush=True)
        except:
            print(u.timestamp() + ": An error occured while running: " + __file__, flush=True)
            u.display_alert(r"An error occured while running: " + __file__, blocking=False)
            self.observer.stop()
            self.observer.join()


class AmazonPDFHandler(FileSystemEventHandler):
    ps_pdf_receive_time = None  # seconds since epoch
    ps_pdf_path = None

    @staticmethod
    def on_created(event):
        path_to_source_pdf = event.src_path
        print(u.timestamp() + ": Started receiving Amazon-PDF: '" + path_to_source_pdf + "'", flush=True)

        if u.dir_len(AMAZON_VP_DESTINATION_FOLDER) == 1:
            # received file is the 1st pdf of an amazon pdf-pair and will be treated as the ps_pdf
            AmazonPDFHandler.ps_pdf_receive_time = int(time.time()) # seconds since epoch
            AmazonPDFHandler.ps_pdf_path = path_to_source_pdf
        elif u.dir_len(AMAZON_VP_DESTINATION_FOLDER) == 2:
            seconds_since_epoch = int(time.time())

            if seconds_since_epoch - AmazonPDFHandler.ps_pdf_receive_time <= WAIT_TIME_FOR_2ND_PDF: # the 2nd pdf came under time, treat it as the sl_pdf
                sl_pdf_path = path_to_source_pdf
                u.do_amazon_print_job(AmazonPDFHandler.ps_pdf_path, sl_pdf_path)
                u.empty_or_make_new(AMAZON_VP_DESTINATION_FOLDER)
            else: # the 2nd pdf did NOT come under time, treat the 2nd pdf as ps_pdf and delete everything else
                # delete everything but the pdf just received:
                dir_items = glob.glob(AMAZON_VP_DESTINATION_FOLDER + "*")
                dir_items.remove(path_to_source_pdf)
                for item in dir_items:
                    os.remove(item)
                
                AmazonPDFHandler.ps_pdf_path = path_to_source_pdf  # treat it as the first pdf/ps_pdf of the complete pair
                AmazonPDFHandler.ps_pdf_receive_time = time.time() # seconds since epoch
        else:
            print(u.timestamp() + ": Something unexpected happened. Cleaning " + AMAZON_VP_DESTINATION_FOLDER, flush=True)
            u.empty_dir(AMAZON_VP_DESTINATION_FOLDER)

        
if __name__ == '__main__':
    print("\n\n" + u.timestamp() + ": " + __file__ + " started", flush=True)
    
    w = AmazonWatcher()
    w.start()
