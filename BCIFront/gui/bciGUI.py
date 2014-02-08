import sys, os
import json
import socket
from PySide import QtGui, QtCore
from BCIFront.classifier.naiveFormats import FormatJson
from BCIFront.classifier.naive import NaiveBayes
from BCIFront.gui.bciHelper import bciComms
from math import sin, cos, radians
from Queue import Queue
import random
from multiprocessing import Process, Value, Pipe, Queue as multiQueue
import ctypes
import winsound

class BciMain(QtGui.QMainWindow):

    def __init__(self):
        self.IP = '127.0.0.1' # socket.gethostname()
        self.classifier = None
        self.trainingDataFormater = None
        # Default values
        self.settings = {"port": 7337, "numTrials": 10, "trialLength": 10,
                "channels": {},
                "freqMap": {
                    "15 Hz": {"x": 200, "y": 900, "theta": 270},
                    "22 Hz": {"x": 1480, "y": 900, "theta": 270},
                    "17 Hz": {"x": 1560, "y": 760, "theta": 0},
                    "20 Hz": {"x": 120, "y": 750, "theta": 180},
                    "12 Hz": {"x": 820, "y": 900, "theta": 270},

                    "25 Hz": {"x": 1090, "y": 750, "theta": 270}
                    }
                }
        self.directory = os.path.dirname(os.path.realpath(__file__))
        self.settingsFile = os.path.join(self.directory, "config.json")
        super(BciMain, self).__init__()

        # Read in settings file ("config.json")
        self.loadSettings()

        # Set up the menu bar
        self.toolBar()

        # Add option dialog for loading a file or
        # starting a training session
        self.initialPrompt()

        # Networking to BCI
        self.sendPacket = Value(ctypes.c_bool, False, lock=False)
        self.pipeReceive, self.pipeSend = Pipe(True)
        self.proc = Process(target=bciComms.bciConnection, args=(self.IP, int(self.settings["port"]), self.sendPacket, self.pipeSend))
        self.proc.start()

        self.headerRegex = r"SourceTime[\s]+([0-9]+)"
        self.sendPacket.value = True
        self.endPacketRegex = bciComms.determineEndRegex(self.pipeReceive)
        print self.endPacketRegex
        self.sendPacket.value = False

        # Set size and title
        self.setGeometry(300, 300, 640, 480)
        self.center()
        self.setWindowTitle('BCI Operator')

        # Bring to forefront
        self.show()
        self.raise_()

    def closeEvent(self, event):
        """ On close it closes the socket """
        if self.proc.is_alive():
            self.proc.terminate()

    def writeFile(self, data, trial, channel):
        f = open("temp/"+str(trial)+str(channel)+".txt", 'w')

        for d in data:
            f.write(d)

    def trainingScreen(self):
        """ Displays a training screen that displays arrows to different frequency lights
        and records the data within each of these periods. Saves this data in a JSON file """
        window = drawWidget(self)

        # Creates a random ordering of the trials
        channels = [str(i) for i in self.settings["channels"].values()
                    if not i == "None"]
        trials = self.settings["numTrials"]
        time = self.settings["trialLength"]
        bciData = {}

        for t in range(trials):
            print (t+1), "/", trials
            random.shuffle(channels)
            bciData[t] = {}

            for c in channels:
                # Setup
                param = self.settings["freqMap"][c]
                q = multiQueue()

                window.drawCrossTimed(0.4, 3, True)

                # Starting storing packets sent through the pipe when a
                # batch arriving from BCI2000 completes. This is signalled
                # by the last Signal(X,Y) received.
                self.sendPacket.value = True
                lastStamp = bciComms.discardTill(self.pipeReceive, self.endPacketRegex, self.headerRegex)
                lastStamp = int(lastStamp)

                collectProc = Process(target=bciComms.collectData,
                        args=(self.pipeReceive, time, self.headerRegex, self.endPacketRegex, q, lastStamp))
                collectProc.start()

                window.drawArrowTimed(param["x"], param["y"], 200, param["theta"], time, True)

                bciData[t][c] = q.get()

                self.writeFile(bciData[t][c], t, c)
                self.sendPacket.value = False

        # Write the training data to a file, and get the formated training data
        fName, _ = QtGui.QFileDialog.getSaveFileName(self, "Save the test data", "", "JSON (*.json)", "JSON (*.json)")

        # User didn't pick a filename, ask them again and if repeated return
        if fName == "":
            self.showMessage("You didn't select a file! Try again otherwise data is lost")
            fName, _ = QtGui.QFileDialog.getSaveFileName(self, "Save the test data", "", "JSON (*.json)", "JSON (*.json)")

            if fName == "":
                window.close()
                return

        formatedJson = None

        # List of frequencies collected on
        freqList = [int(x.split(" ")[0]) for x in channels]
        freqList.sort()

        with open(fName, "w") as f:
            formatedJson = bciComms.processTrainData(bciData, freqList, f)

        # Saves the training data to the instance field, trains the classifier and transitions to run screen
        self.trainingDataFormater = FormatJson(formatedJson, loadDict=True)
        if self.trainClassifier():
            self.transitionToRun()

        window.close()

    def trainClassifier(self):
        """ Trains the classifier. If any error occurs, it prints the exception.
        Returns true if training was successful and false otherwise """
        try:
            self.classifier = NaiveBayes(self.trainingDataFormater.data())
            return True
        except Exception as e:
            BciMain.showMessage("Could not train classifier. Error:\n" + str(e))
            return False

    def transitionToRun(self):
        """ Sets the main bci app to display a run button to start a run. This
        should only happen after the classifier was properly trained """
        # Layout manager
        hbox = QtGui.QHBoxLayout()
        widget = QtGui.QWidget()

        # Buttons
        btn1 = QtGui.QPushButton("Start Run", widget)
        btn1.clicked.connect(self.runScreen)

        hbox.addWidget(btn1)
        widget.setLayout(hbox)
        self.setCentralWidget(widget)

    def runScreen(self):
        from BCIFront.gui.questions import questionsRunScreen
        self.run = questionsRunScreen(self, self.classifier)

    # Reads in file and updates dictionary. If it doesn't exist
    # it is created with default values
    def loadSettings(self):
        """ Loads settings from the config.json file in the directory containing
        this file. If the file doesn't exist, as would be the case on the first
        run, the file is made with default settings
        """
        # Try to open file
        try:
            jFile = open(self.settingsFile, "r")
        except IOError:
            # Doesn't exist so we create it
            jFile = open(self.settingsFile, "w")
            json.dump(self.settings, jFile)
            return

        # Try to parse json file
        try:
            self.settings = json.load(jFile)
            #print self.settings
            #print "File: " + json.load(jFile)
        except ValueError:
            self.showMessage("""Could not load settings file.\n
                             To reset, delete the config.json file""")


    def center(self):
        """ Centers the application in the middle of the screen """
        qr = self.frameGeometry()
        cp = QtGui.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())


    def initialPrompt(self):
        """ Returns a widget that contains the buttons to either load a
        training or start a new one """

        # Layout manager
        hbox = QtGui.QHBoxLayout()
        widget = QtGui.QWidget()

        # Buttons
        btn1 = QtGui.QPushButton("Start Training", widget)
        btn1.clicked.connect(self.trainingScreen)

        btn2 = QtGui.QPushButton("Load Train File", widget)
        btn2.clicked.connect(self.loadFile)

        hbox.addWidget(btn1)
        hbox.addWidget(btn2)
        widget.setLayout(hbox)
        self.setCentralWidget(widget)


    def toolBar(self):
        """ Creates a tool bar for the main application """

        ipAction= QtGui.QAction('&IP', self)
        ipAction.triggered.connect(self.showIP)

        settingAction = QtGui.QAction('&Settings', self)
        settingAction.setStatusTip('Settings Page')
        settingAction.triggered.connect(self.settingsPage)

        trainScreenAction = QtGui.QAction('&Train Screen', self)
        trainScreenAction.setStatusTip('Training Screen')
        trainScreenAction.triggered.connect(self.initialPrompt)

        exitAction = QtGui.QAction('&Exit', self)
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.close)

        self.toolbar = self.addToolBar("Bar")
        self.toolbar.addAction(ipAction)
        self.toolbar.addAction(settingAction)
        self.toolbar.addAction(trainScreenAction)
        self.toolbar.addAction(exitAction)

    def showIP(self):
        """ Displays a dialog showing the computers IP. This is usefully
        when setting the BCI2000 output parameter
        """

        # Get IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("gmail.com",80))
            ip = s.getsockname()[0]
            self.showMessage("IP: " + ip + "\nHostname: " + socket.gethostname())
        except socket.error as e:
            self.showMessage("""Could not find IP. Possibly not connected to
                           internet. Error code: \n\n""" + str(e))

        finally:
            s.close()

    @classmethod
    def showMessage(cls, string):
        """ Shows a popup screen with the given message """

        msgBox = QtGui.QMessageBox()
        msgBox.setText(string)
        msgBox.show()
        msgBox.raise_()
        msgBox.exec_()


    def settingsPage(self):
        """ Pops up a setting page and then on exit, updates the settings
        and saves them to a file
        """
        s = SettingsPage(self.settings)
        if s.exec_() == QtGui.QDialog.Accepted:
            self.settings["port"] = int(s.portEdit.text())
            self.settings["numTrials"] = int(s.trialNumbEdit.text())
            self.settings["trialLength"] = int(float(s.trialLengthEdit.text()))
            self.settings["channels"] = {}


            # Create a dictionary of the channels to their set index
            for i, combo in enumerate(s.channelValues):
                self.settings["channels"][str(i)] = combo.currentText()

            jFile = open(self.settingsFile, "w")
            json.dump(self.settings, jFile)

    # Prompts for a file and then formats it and saves the list
    # of [("label", [data])] to an instance variable
    def loadFile(self):
        """ Prompts the user for a training file and if it is appropriately formated,
        trains the classifier. Supports both old matlab format and the json format
        generated by this program
        """
        fname, _ = QtGui.QFileDialog.getOpenFileName(self, 'Open file')

        if fname == "":
            self.showMessage("No file was trained with!")
            return

        try:
            formater = FormatJson(fname)
            self.trainingDataFormater = formater

            if self.trainClassifier():
                self.transitionToRun()
        except Exception as e:
            self.showMessage("Couldn't open file: \n" + str(e))

class robotControlRunScreen():
    def __init__(self, parent, classifier):
        """ Initializes the screen and then displays a new window
        Args:
            parent: the calling class. Expected to be BciMain
            classifier: a classifier with a predict method that has already been
            trained
        """
        self.screen = drawWidget(parent)
        self.coms = Communicate()
        self.coms.txt.connect(self.handlePrediction)

        self.middle = None

        # Set up labels
        l1 = self.screen.drawText("Left", parent.settings["freqMap"]["20 Hz"]["x"] - 50, parent.settings["freqMap"]["20 Hz"]["y"])
        l2 = self.screen.drawText("Right", parent.settings["freqMap"]["17 Hz"]["x"] - 50, parent.settings["freqMap"]["17 Hz"]["y"])
        l3 = self.screen.drawText("Forward", parent.settings["freqMap"]["22 Hz"]["x"] - 50, parent.settings["freqMap"]["22 Hz"]["y"])
        assert(l1 and l2 and l3)
        l4 = self.screen.drawText2("None", parent.settings["freqMap"]["12 Hz"]["x"] - 50, parent.settings["freqMap"]["12 Hz"]["y"])

        # Create TCP Socket to the robot
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(("chester.cs.washington.edu", 8611))
        except Exception as e:
            print "Couldnt connect to chester"
            print e
            self.screen.close()
            return

        self.helper = robotControlRunScreenHelper(parent, classifier, self.coms)
        self.helper.start()

    def handlePrediction(self, text):
        if self.middle != None:
            self.screen.removeText(self.middle)
        if text == "17 Hz":
            self.middle = self.screen.drawText("Right")
        elif text == "20 Hz":
            self.middle = self.screen.drawText("Left")
        elif text == "22 Hz":
            self.middle = self.screen.drawText("Forward")
        else:
            self.middle = self.screen.drawText(text)

        # if text == "17 Hz":
            # self.sock.send("1\n")
        # elif text == "20 Hz":
            # self.sock.send("2\n")
        # elif text == "22 Hz":
            # self.sock.send("0\n")

        winsound.PlaySound("ding.wav", winsound.SND_FILENAME)
            
    def closeEvent(self, event):
        self.parent.sendPacket.value = False
        if self.helper.isRunning():
            self.helper.terminate()

        self.sock.close()

class robotControlRunScreenHelper(QtCore.QThread):
    def __init__(self, parent, classifier, coms):
        super(robotControlRunScreenHelper, self).__init__()
        self.parent = parent
        self.classifier = classifier
        self.coms = coms

        self.timeout = 3 # seconds till it forces a classification
        self.period = 0.5 # the time between bci2000 headers
        self.threshold = 0.95 # The confidence when to display the classification

    def run(self):
        count = 0
        previous = {} # Used to keep track of previous predictions
        self.parent.sendPacket.value = True
        q = multiQueue()
        last = bciComms.discardTill(self.parent.pipeReceive, self.parent.endPacketRegex, self.parent.headerRegex)
        last = int(last)

        collecting = True

        while True:
            count += 1
            last = bciComms.collectData(self.parent.pipeReceive, self.period, self.parent.headerRegex,
                    self.parent.endPacketRegex, q, last)
            data = q.get()

            # Takes the raw data and decomposes it into a dict of the corresponding terms
            processed = bciComms.rawToDict(data)
            classWith = self.parent.trainingDataFormater.formatFrequencies(processed["Raw FFT"])

            prediction = None
            accuracy = None

            try:
                prediction, accuracy = self.classifier.predict(classWith)
            except Exception:
                continue

            # Changed what predict returns
            accuracy = accuracy[prediction]

            if count * self.period < self.timeout and collecting:
                if not previous.has_key(prediction):
                    previous[prediction] = 0.0

                previous[prediction] += accuracy

            elif collecting:
                likely = sorted(previous, key=previous.get, reverse=True)[0]

                if previous[likely] < count * self.threshold:
                    self.coms.txt.emit("None")
                else:
                    self.coms.txt.emit(likely)

                previous = {}
                count = 0
                collecting = False
            elif count * self.period < self.timeout and not collecting:
                self.coms.txt.emit("Robot Moving")
            elif not collecting:
                collecting = True
                count = 0
                self.coms.txt.emit("")

class drawWidget(QtGui.QMainWindow):

    def __init__(self, parent):
        super(drawWidget, self).__init__(parent)

        self.parent = parent
        # [((x1,y1),(x2,y2))]
        self.lines = []
        self.text = []
        self.threads = []
        self.updateQueue = Queue()

        self.font = QtGui.QFont('Helvetica', 48)

        # Signals and Slots
        self.com = Communicate()
        self.com.speak.connect(self.removeLine)
        self.com.up.connect(self.refresh)

        self.setLayout(QtGui.QVBoxLayout())

        self.toolBar()
        self.secondScreen()
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.show()

    # Move to second screen
    def secondScreen(self):
        desk = QtGui.QDesktopWidget()

        if desk.numScreens() < 1:
            self.showMaximized()
        else:
            qr = self.frameGeometry()
            geom = desk.availableGeometry(1)
            self.setGeometry(geom)
            qr.moveCenter(geom.center())
            self.move(qr.topLeft())
            self.showMaximized()

    def toolBar(self):
        """ Creates a tool bar for the main application """
        exitAction = QtGui.QAction('&Exit', self)
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.close)

        self.toolbar = self.addToolBar("Bar")
        self.toolbar.addAction(exitAction)

    def closeEvent(self, event):
        self.lines = []
        for proc in self.threads:
            if proc.isRunning():
                proc.exit()

    def paintEvent(self, event):
        qp = QtGui.QPainter()
        qp.begin(self)

        pen = QtGui.QPen(QtCore.Qt.black, 2, QtCore.Qt.SolidLine)
        qp.setPen(pen)
        qp.setFont(self.font)

        for p in self.lines:
            qp.drawLine(p[0][0], p[0][1], p[1][0], p[1][1])

        for t,x,y in self.text:
            qp.drawText(x,y,unicode(t))

        qp.end()

    def drawText(self, text, x=None, y=None, xOff=0, yOff=0):
        val = None

        if x==None and y==None:
            center = self.rect().center()
            val = [text, center.x(), center.y()]
        else:
            val = [text, x, y]


        # Center it
        fm = QtGui.QFontMetrics(self.font)
        width = fm.width(text)

        val[1] += xOff - (width / 2.0)
        val[2] += yOff
        self.text.append(val)
        self.update()
        QtCore.QCoreApplication.processEvents()
        return val

    def removeText(self, text):
        if text in self.text:
            self.text.remove(text)
            self.update()
            QtCore.QCoreApplication.processEvents()

    # points = ((x1,y1),(x2,y2))
    def drawLine(self, point):
        self.lines.append(point)
        self.update()
        return point

    def drawLineTimed(self, point, time):
        ref = self.drawLine(point)
        timed = TimedDrawing(self, [ref], time)
        timed.finished.connect(self.workerFinished)
        self.threads.append(timed)
        timed.start()

    # points = [((x1,y1),(x2,y2)), ((),()),...]
    # returns a list of points
    def drawLines(self, points):
        self.lines.extend(points)
        self.update()
        return points

    def drawLinesTimed(self, points, time, blocking=False):
        ref = self.drawLines(points)
        timed = TimedDrawing(self, ref, time)
        timed.finished.connect(self.workerFinished)
        self.threads.append(timed)
        timed.start()

        if blocking:
            while not timed.isFinished():
                QtCore.QCoreApplication.processEvents()

    def drawCross(self, ratio):
        geom = self.frameGeometry()
        height = geom.height()
        width = geom.width()
        center = (width / 2.0, height / 2.0)

        wOffset = ratio * (width / 2.0)
        line1 = ((center[0] - wOffset, center[1]),
                (center[0] + wOffset, center[1]))

        hOffset = ratio * (height/ 2.0)
        line2 = ((center[0], center[1] - hOffset),
                (center[0], center[1] + hOffset))

        return self.drawLines([line1, line2])

    def drawCrossTimed(self, ratio, time, blocking=False):
        ref = self.drawCross(ratio)
        timed = TimedDrawing(self, ref, time)
        timed.finished.connect(self.workerFinished)
        self.threads.append(timed)
        timed.start()

        if blocking:
            while not timed.isFinished():
                QtCore.QCoreApplication.processEvents()

    # theta = 0/360 points right, 90 up, 180 left...
    def drawArrow(self, x, y, length, theta):
        half = length / 2.0
        rad = radians(theta % 360)
        x1 = half * cos(rad)
        y2 = half * sin(rad)
        p1 = (x+x1, y-y2)
        p2 = (x-x1, y+y2)
        line1 = (p1,p2)

        a1 = drawWidget.pointTransform((p2,p1), .3, 45)
        line2 = (p1,a1)

        a2 = drawWidget.pointTransform((p2,p1), .3, -45)
        line3 = (p1,a2)

        refs = [line1, line2, line3]
        self.drawLines(refs)
        return refs

    def drawArrowTimed(self, x, y, length, theta, time, blocking=False):
        ref = self.drawArrow(x,y,length, theta)
        timed = TimedDrawing(self, ref, time)
        timed.finished.connect(self.workerFinished)
        self.threads.append(timed)
        timed.start()

        if blocking:
            while not timed.isFinished():
                QtCore.QCoreApplication.processEvents()


    #x = x1 - [(x1-x0)cos(t) - (y1-y0)sin(t)]*d/l
    #y = y1 - [(y1-y0)cos(t) + (x1-x0)sin(t)]*d/l
    # Given a point p, a ratio of arrow length to line length, and an angle
    # for the arrow head, returns a point for the tip of the arrow line
    @classmethod
    def pointTransform(cls, p, ratio, theta):
        xDif = p[1][0] - p[0][0]
        yDif = p[1][1] - p[0][1]

        x = p[1][0] - (xDif*cos(theta) - yDif*sin(theta)) * ratio
        y = p[1][1] - (yDif*cos(theta) + xDif*sin(theta)) * ratio
        return (x,y)

    # Deletes references to finished threads so they can be GC'd
    def workerFinished(self):
        filter(lambda t: not t.isFinished(), self.threads)

    @QtCore.Slot(tuple)
    def removeLine(self, line):
        self.lines.remove(line)
        #self.update()

    @QtCore.Slot()
    def refresh(self):
        if not self.updateQueue.empty():
            self.updateQueue.get()
            self.update()

# Allows you to have temporary lines displayed
class TimedDrawing(QtCore.QThread):
    def __init__(self, drawWid, refs, time):
        super(TimedDrawing, self).__init__()
        self.com = drawWid.com
        self.draw = drawWid
        self.refs = refs
        self.time = time

    def run(self):
        import time
        time.sleep(self.time)

        # For each reference emit a signal
        # acts as a way of removing it from the screen
        for r in self.refs:
            self.com.speak.emit(r)

        self.draw.updateQueue.put(self)
        self.com.up.emit()

# Only subclasses of QObject can act as a generic signal. This
# is used to tell the window to delete a certain line
class Communicate(QtCore.QObject):
    speak = QtCore.Signal(tuple)
    up = QtCore.Signal()
    txt = QtCore.Signal(str)

# Displays a setting page
class SettingsPage(QtGui.QDialog):
    def __init__(self, settings, parent=None):
        super(SettingsPage, self).__init__(parent)
        self.setWindowTitle(self.tr('Settings Page'))

        # Get Text
        portText        = settings.get("port")
        numText         = settings.get("numTrials")
        trialLengthText = settings.get("trialLength")

        # Labels
        portLabel        = QtGui.QLabel('BCI 2000 Port')
        trainLabel       = QtGui.QLabel('Training:')
        trialNumbLabel   = QtGui.QLabel('Trials / Channel')
        trialLengthLabel = QtGui.QLabel("Trial Length (sec)")

        # Text input
        self.portEdit        = QtGui.QLineEdit(unicode(portText))
        self.trialNumbEdit   = QtGui.QLineEdit(unicode(numText))
        self.trialLengthEdit = QtGui.QLineEdit(unicode(trialLengthText))

        # Channels
        channels = QtGui.QLabel("SSVEP Channels:")
        chanList = [QtGui.QLabel("Channel " + str(i+1)) for i in range(6)]

        # Drop downs
        values = ["None", "12 Hz", "15 Hz", "17 Hz", "20 Hz", "22 Hz", "25 Hz"]
        self.channelValues = []

        for i in range(len(chanList)):
            temp = QtGui.QComboBox()
            temp.addItems(values)

            if str(i) in settings["channels"]:
                index = 0

                try:
                    index = values.index(settings["channels"][str(i)])
                except ValueError:
                    pass

                temp.setCurrentIndex(index)

            self.channelValues.append(temp)


        # Buttons
        ok     = QtGui.QPushButton("OK")
        cancel = QtGui.QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        ok.clicked.connect(self.readSettings)

        grid = QtGui.QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(portLabel, 1, 0)
        grid.addWidget(self.portEdit, 1, 1)
        grid.addWidget(trainLabel, 2, 0)
        grid.addWidget(trialNumbLabel, 3,0)
        grid.addWidget(self.trialNumbEdit, 3, 1)
        grid.addWidget(trialLengthLabel, 4, 0)
        grid.addWidget(self.trialLengthEdit, 4, 1)
        grid.addWidget(channels, 5, 0)

        for i,lab in enumerate(chanList):
            grid.addWidget(lab, 6+i, 0)
            grid.addWidget(self.channelValues[i], 6+i, 1)

        grid.addWidget(cancel, 12, 0)
        grid.addWidget(ok, 12, 1)

        # Displaying page
        self.setLayout(grid)
        self.show()

    def readSettings(self):
        self.accept()


def main():
    app = QtGui.QApplication(sys.argv)
    b = BciMain()
    assert b
    sys.exit(app.exec_())
