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

USE_LOG_FILE                              = False # if False, print log to the the stdout which is the terminal usually
LOG_FILE_PATH                             = os.getcwd() + os.sep + __file__ + ".log"
AMAZON_VP_DESTINATION_FOLDER              = os.getcwd() + os.sep + "amazon_virtual_printer_target/"  # '/' at the end is important
WAIT_TIME_FOR_2ND_PDF                     = 240 # in seconds
WAIT_TIME_FOR_LETTING_FILES_TRANSER_FULLY = 10
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
        u.log("Ready to receive a new amazon pdf-pair.\n\n")

        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            u.log("Closing all threads, please wait...")
            self.observer.stop()
            self.observer.join()
            u.log("Done")
        except:
            u.log("An error occured while running: " + __file__)
            u.display_alert(r"An error occured while running: " + __file__, blocking=False)
            self.observer.stop()
            self.observer.join()


class AmazonPDFHandler(FileSystemEventHandler):
    ps_pdf_receive_time = None 
    ps_pdf_path = None

    @staticmethod
    def on_created(event):
        path_to_source_pdf = event.src_path
        u.log("Started receiving Amazon-PDF: '" + path_to_source_pdf + "'")

        if u.dir_len(AMAZON_VP_DESTINATION_FOLDER) == 1:
            AmazonPDFHandler.ps_pdf_receive_time = int(time.time())
            AmazonPDFHandler.ps_pdf_path = path_to_source_pdf
        elif u.dir_len(AMAZON_VP_DESTINATION_FOLDER) == 2:
            seconds_since_epoch = int(time.time())

            if seconds_since_epoch - AmazonPDFHandler.ps_pdf_receive_time <= WAIT_TIME_FOR_2ND_PDF: # the 2nd pdf came under time, treat it as the sl_pdf
                time.sleep(WAIT_TIME_FOR_LETTING_FILES_TRANSER_FULLY)
                
                u.do_amazon_print_job(AmazonPDFHandler.ps_pdf_path, path_to_source_pdf)
                
                u.empty_or_make_new(AMAZON_VP_DESTINATION_FOLDER)
                u.log("Amazon print job completed")
                u.log("Ready to receive a new amazon pdf-pair.\n\n")
            else: # the 2nd pdf did NOT come under time, treat the 2nd pdf as ps_pdf and delete everything else
                u.empty_dir(AMAZON_VP_DESTINATION_FOLDER, path_to_source_pdf)
                
                AmazonPDFHandler.ps_pdf_path = path_to_source_pdf  # treat it as the first pdf of the complete pair
                AmazonPDFHandler.ps_pdf_receive_time = time.time()
        else:
            u.log("More than 2 files detected in " + AMAZON_VP_DESTINATION_FOLDER)
            time.sleep(WAIT_TIME_FOR_LETTING_FILES_TRANSER_FULLY)
            u.empty_dir(AMAZON_VP_DESTINATION_FOLDER)

        
if __name__ == '__main__':
    u.log(__file__ + " started")
    
    w = AmazonWatcher()
    w.start()
