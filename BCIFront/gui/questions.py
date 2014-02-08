from BCIFront.gui.bciGUI import drawWidget, Communicate
from BCIFront.gui.bciHelper import bciComms
from PySide import QtCore
from multiprocessing import Queue as multiQueue
import os
import socket
import uuid
import logging
from time import time

class questionsRunScreen():
    def __init__(self, parent, classifier):
        """ Initializes the screen and then displays a new window
        Args:
            parent: the calling class. Expected to be BciMain
            classifier: a classifier with a predict method that has already been
            trained
        """
        self.middle = None
        self.answer = None
        self.new = False
        self.screen = drawWidget(parent)
        self.coms = Communicate()
        self.coms.txt.connect(self.handlePrediction)

        self.screen.drawText("Yes", parent.settings["freqMap"]["20 Hz"]["x"] - 50, parent.settings["freqMap"]["20 Hz"]["y"])
        self.screen.drawText("No", parent.settings["freqMap"]["17 Hz"]["x"] - 50, parent.settings["freqMap"]["17 Hz"]["y"])
        self.screen.keyPressEvent = self.keyPressEvent

        self.helper = questionsRunScreenHelper(parent, self, classifier, self.coms)
        self.helper.start()

        self.sock = self.connect()
        self.server = serverConnection(self.sock, self.coms)
        self.server.start()
        
        # Logging stuff
        if not os.path.exists("logs"):
            os.makedirs("logs")
        logging.basicConfig(filename=('logs/' + str(time()) + "-" + str(uuid.uuid1()) + ".log"), \
            filemode='w', level=logging.DEBUG)
        

    def connect(self):
        TCP_IP = '128.208.7.167'
        TCP_PORT = 10000

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((TCP_IP, TCP_PORT))
        return s

    def keyPressEvent(self, e):
        print "!!!" + str(e.key())
        if e.key() == QtCore.Qt.Key_Y:
            logging.info("Keyboard: Yes")
        elif e.key() == QtCore.Qt.Key_N:
            logging.info("Keyboard: No")
            
    def handlePrediction(self, text):
        if self.middle != None:
            self.screen.removeText(self.middle)

        text = text.strip()
        if text[:8] == "Answer: ":
            print "Argabarga " + text
            if self.answer != None:
                self.screen.removeText(self.answer)

            self.answer = self.screen.drawText("Answer being guessed is " + text[8:], yOff=-100)

        elif text[:12] == "Question is " or text[:8] == "Is it a ":
            print "O_O " + text
            self.middle = self.screen.drawText(text)
            self.new = True
        elif text == "20 Hz":
            self.sock.send("yes")
            logging.info(text)
            print "Emit - yes"
        elif text == "17 Hz":
            self.sock.send("no")
            logging.info(text)
            print "Emit - no"
        elif text[:3] == "TMS":
            logging.info(text)
        else:
            print "X_X " + text

class questionsRunScreenHelper(QtCore.QThread):
    def __init__(self, parent, runner, classifier, coms):
        super(questionsRunScreenHelper, self).__init__()
        self.parent = parent
        self.runner = runner
        self.classifier = classifier
        self.coms = coms

        self.timeout = 5 # seconds till it forces a classification
        self.period = 0.5 # the time between bci2000 headers
        self.threshold = 10 # The confidence when to display the classification

    def run(self):
        self.parent.sendPacket.value = True
        q = multiQueue()
        last = bciComms.discardTill(self.parent.pipeReceive, self.parent.endPacketRegex, self.parent.headerRegex)
        last = int(last)

        count = 0
        priors = self.classifier.priors

        while True:
            newQuestion = self.runner.new

            last = bciComms.collectData(self.parent.pipeReceive, self.period, self.parent.headerRegex,
                    self.parent.endPacketRegex, q, last)
            data = q.get()

            # A new question has not arrived
            if not newQuestion:
                continue

            count += 1
            # Want to give the user a second to read the text and ignore the brain signals
            if count * self.period < 1.0: continue

            # Takes the raw data and decomposes it into a dict of the corresponding terms
            processed = bciComms.rawToDict(data)
            classWith = self.parent.trainingDataFormater.formatFrequencies(processed["Raw FFT"])
            logging.info(processed["Raw FFT"])
            

            probs = None
            try:
                _, probs = self.classifier.predict(classWith)
            except Exception:
                continue

            # Updating priors
            for k,v in probs.iteritems():
                priors[k] *= v

            # Renormalizing
            s = sum(priors.values())
            priors = {k: priors[k] / s for k in priors}

            print count
            
            # Emit prediction if time has exceeded 6 seconds or hit threshold
            highest = max(priors, key=lambda k: priors[k])
            if count * self.period >= 6.0 or priors[highest] >= self.threshold:
                self.coms.txt.emit(highest)
                self.runner.new = False
                count = 0
                priors = self.classifier.priors

class serverConnection(QtCore.QThread):
    def __init__(self, sock, coms):
        super(serverConnection, self).__init__()
        self.sock = sock
        self.coms = coms

    def run(self):
        lastFull = True
        last = ""

        while True:
            data = self.sock.recv(1024)

            for data, full in bciComms.tcpYielder(data):
                if not full:
                    last += data
                    lastFull = False
                    continue
                elif full and not lastFull:
                    lastFull = True
                    data = last + data
                    last = ""

                self.coms.txt.emit(data)

