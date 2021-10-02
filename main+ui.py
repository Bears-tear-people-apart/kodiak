import cv2, sys, os, serial, threading, time
import numpy as np
from PIL import Image
from playsound import playsound
from yolo import YOLO, detect_video
from PyQt5 import QtCore, QtWidgets, QtGui

class CovidInspectionSystem:
    def __init__(self): #__init__은 클래스 생성자이다. 클래스가 인스턴스를 생성할 때에 호출되는 특별한 메소드(method)이다. init 앞과 뒤에 붙은 __은 파이썬이 자동으로 호출하는 메소드를 명시한 것이다.
    #self는 인스턴스 자기 자신을 의미한다. 클래스로 만든 객체를 인스턴스라 한다. 인스턴스를 생성하며 함께 전달받은 인자 값을 __init__생성자에서 멤버변수에 전달한다.
        self.__initArduino() 
        self.__initModel()
        
    def __del__(self):
        self.capture.release()

    def __initArduino(self):
        print('set arduino')
        self.ser = serial.Serial(
            port='COM3',
            baudrate=9600,
        )

    def __initModel(self):
        print("Load trained model...")
        self.yolo = YOLO(model_path='./logs/009/trained_weights_final.h5',
                    anchors_path='./model_data/yolo_anchors.txt',
                    classes_path='./model_data/voc_classes.txt',
                score=0.5)

        print("Set camera...")
        self.capture = cv2.VideoCapture(0)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        print('Initialize session...')
        self.detectFace()

    def readSerial(self):
        dist, temp = 100, -1
        data = None
        if self.ser.readable():
            try:
                res = self.ser.readline()
                data = res.decode()[:len(res)-2]
                
                if data == "Finish":
                    print("finish")
                    global finish
                    finish = 1
                else:
                    data = data.split("[Distance]")
                    
                    if len(data) > 1:
                        dist, temp = data[1].split("[Temp]")
                        dist = int(dist)
                        temp = float(temp)
                    
            except:
                #print(dist, temp)
                #print(dist, temp)
                dist, temp = 100, 0
        
        return dist, temp

    def writeSerial(self, op):
        try:
            self.ser.write(op.encode())
            if op == 'b' or op == 'c':
                global state
                state = 0
        except:
            print("failed to write")
        
    def detectFace(self):
        ret, frame = self.capture.read()
        frame = Image.fromarray(frame)
        detected_frame, det_class = self.yolo.detect_image(frame)
        return frame, det_class
    
    def cameraInfo(self):
        ret, image = self.capture.read()
        height, width = image.shape[:2]
        return height, width
         
    def getScreen(self):
        ret, frame = self.capture.read()
        return frame

class ShowVideo(QtCore.QThread):
    #signals
    video_signal = QtCore.pyqtSignal(QtGui.QImage)
    subtitle_signal = QtCore.pyqtSignal(str)
    temperature_signal = QtCore.pyqtSignal(float)

    def __init__(self, parent=None):
        super(ShowVideo, self).__init__(parent) 
    
    def setSubtitle(self, number, delay=0):
        text = [
            '',
            'QR코드를 입력해주세요', #1
            '손소독을 해주세요. 손소독 후 문이 열립니다', #2
            '비정상 체온입니다. 처음부터 다시 진행해주세요', #3
            '체온을 측정 중입니다', #4
            '마스크를 착용여부와 체온을 확인합니다.', #5
            '정상입니다.', #6
            '마스크 착용이 올바르지 않습니다. 처음부터 다시 진행해주세요' #7
        ]
        time.sleep(delay)
        subtitle  = text[number]
        self.subtitle_signal.emit(subtitle)

    def setSound(self, number, b=False):
        playsound("./mp3/{}.mp3".format(number), block=b)

    @QtCore.pyqtSlot()
    def run(self):
        print("Start System.")
        #0
        os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
        model = CovidInspectionSystem() 
        height, width = model.cameraInfo()
        frame_cnt = 0
        mask_cnt = 0 

        global timer
        timer = 0
        
        global finish
        finish = 0
        
        temp_timer = 0

        #1
        name_on = 0
        self.name = None

        #2
        #마스크 착용 기준 : 30프레임 -> 약 1초
        mask_on = 0
        mask_cnt = 0
        mask_max = 30

        #3
        #온도 측정 개수, 온도 = 10개 평균
        #5cm 이내에서 측정
        dist = 50  #거리
        temp_on = 0  #온도 측정 개수 초기값0
        temp_max = 10 #10번 측정함
        temp_cnt = 0 #현재 온도 측정 횟수
        self.temp = 0 #측정한 온도

        #initial
        self.setSound(1)
        self.setSubtitle(1)

        # main loop
        while True:
            # 시리얼 입력 확인
            # 얼굴 인식
            d, t = model.readSerial() 
            frame = model.getScreen()
            
            if finish == 1:
                print("f")
                self.temperature_signal.emit(-1)
                self.setSubtitle(1)
                self.setSound(1)
                finish = 0

            #1. 이름 입력
            if not name_on:
                if not (self.name is None):
                    print("name on")
                    timer = 120
                    name_on = 1
                    self.setSound(5)  #마스크 착용여부와 체온을 확인합니다.
                    self.setSubtitle(5)

            #2. 마스크 착용 여부 판단
            elif not mask_on:

                frame, det_class = model.detectFace()
                mask = det_class == 'face_with_mask'

                if mask:
                    timer -= 1
                    mask_cnt += 1
                else:
                    timer -= 1
                    mask_cnt = 0

                if mask_cnt == mask_max:
                    print("mask on")
                    mask_cnt = 0
                    mask_on = 1
                    temp_timer = 300
                    self.setSound(99) #체온을 측정 중입니다.
                    self.setSubtitle(4)
                elif timer <= 0:
                    print("No Mask!!")
                    mask_cnt = 0
                    self.setSubtitle(7) # 마스크 착용이 올바르지 않습니다. 처음부터 다시 진행해주세요.
                    self.setSound(7, True)
                    mask_on = temp_on = name_on = 0
                    self.name = None
                    self.temp = 0
                    self.temperature_signal.emit(-1)
                    self.setSound(1)
                    self.setSubtitle(1)

            #3. 거리가 50 이하 & 마스크 착용 확인 -> 온도 측정
            elif d < dist:
                if temp_cnt != temp_max:  #온도를 max번 만큼 측정하지 않았다면
                    self.temp += t   #t는 측정한 온도를 의미한다. 온도를 10번 측정하면서, 측정 할때마다 그 값을 self.temp 변수에 저장한다.
                    temp_cnt += 1   #현재 측정 횟수 1 더한다
                else:
                    print('temp on')
                    self.temp /= temp_max  #/=연산자: 왼쪽 변수에 오른쪽 변수를 나누고 그 결과를 왼쪽 변수에 할당한다. ex) a/=b는 a=a/b를 의미한다. max번 측정해서 모두 더한 self.temp를 다시 max로 나눔으로써 측정한 온도의 평균값을 구한다.
                    self.temp += 6
                    self.temperature_signal.emit(self.temp)
                    temp_cnt = 0
                    temp_on = 1
                    temp_on = 1
                    
            elif d > dist and mask_on == 1:
                temp_timer -= 1
                if temp_timer <= 0:
                    print("No temp")
                    mask_on = temp_on = name_on = 0
                    self.name = None
                    self.temp = 0
                    self.temperature_signal.emit(-1)
                    self.setSound(1) #qr코드를 입력해주세요
                    self.setSubtitle(1)

            #4 문 열기
            if name_on and mask_on and temp_on:
                op = ''
                if self.temp > 33 and self.temp < 38:
                    self.setSound(2) # 손소독을 해주세요. 손소독 후 문이 열립니다.
                    self.setSubtitle(2)
                    print("door on")
                    op = 'b'
                    f = open( 'data.txt', 'a+')
                    f.write(time.strftime('%c', time.localtime(time.time())) + ' : ' + self.name + '\n')
                    f.close()
                else:
                    #비정상 체온
                    self.setSubtitle(3) #'비정상 체온입니다. 처음부터 다시 진행해주세요'
                    op = 'c'
                    self.setSound(3, True)

                #t = threading.Thread(target=self.setSubtitle, args=(1, 3))
                #t.start()
 
                model.writeSerial(op)
                #time.sleep(7)
                
                mask_on = temp_on = name_on = 0
                self.name = None
                self.temp = 0

                print("write success")



            # 화면 보여주기
            frame = np.array(frame)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qt_image1 = QtGui.QImage(frame.data,
                                    width,
                                    height,
                                    frame.strides[0],
                                    QtGui.QImage.Format_RGB888)
            self.video_signal.emit(qt_image1)

            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(25, loop.quit) #25 ms
            loop.exec_()
            frame_cnt+=1

class ImageViewer(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(ImageViewer, self).__init__(parent)
        self.image = QtGui.QImage()
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawImage(0, 0, self.image)
        self.image = QtGui.QImage()

    def initUI(self):
        self.setWindowTitle('Test')

    @QtCore.pyqtSlot(QtGui.QImage)
    def setImage(self, image):
        if image.isNull():
            print("Viewer Dropped frame!")

        self.image = image
        if image.size() != self.size():
            self.setFixedSize(image.size())
        self.update()

class Form(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Form, self).__init__(parent)
        self.__loadFont()
        self.__setWindowSetting()
        self.__initWidget()

    def __setWindowSetting(self):
        self.setWindowTitle('Anti COVID Security System')
        self.setStyleSheet("background-color: #333333;") 
        self.setGeometry(0,0,880,550)

    def __loadFont(self):
        self.fontDB = QtGui.QFontDatabase()
        for font in os.listdir('./font'):
            self.fontDB.addApplicationFont('./font'+font)

    def __initWidget(self):
        #define widget
        self.vid = ShowVideo()
        self.vid.start()

        self.webcam = ImageViewer()
        self.vid.video_signal.connect(self.webcam.setImage)
        self.vid.subtitle_signal.connect(self.setSubtitle)
        self.vid.temperature_signal.connect(self.setTemperature)

        'subtitle'
        self.subtitle = QtWidgets.QLabel("대기중", self)
        self.subtitle.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.subtitle.setFont(QtGui.QFont('나눔스퀘어', 26))
        self.subtitle.setStyleSheet("color: white; background-color: #333333")
        
        'temperature'
        self.temperature = QtWidgets.QLabel("대기중", self)
        self.temperature.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.temperature.setFixedSize(200, 200)
        self.temperature.setFont(QtGui.QFont('나눔스퀘어 Bold', 42))
        self.temperature.setStyleSheet("color: #333333; background-color: #AAAAAA")
        
        'inputbox'
        self.inputbox = QtWidgets.QLineEdit(self)
        self.inputbox.setStyleSheet("color: #000000; background-color: #FFFFFF")
        self.inputbox.returnPressed.connect(self.setName)
        
        'confirm button'
        self.confirm = QtWidgets.QPushButton("확인",self)
        self.confirm.clicked.connect(self.setName)


        #define layout
        vertical_layout = QtWidgets.QVBoxLayout()
        vertical_layout2 = QtWidgets.QVBoxLayout()
        horizontal_layout = QtWidgets.QHBoxLayout()

        #add vertical2
        vertical_layout2.addWidget(self.temperature)
        vertical_layout2.addWidget(self.inputbox)
        vertical_layout2.addWidget(self.confirm)
        vertical_layout2.setAlignment(self.temperature, QtCore.Qt.AlignTop)
        vertical_layout2.setAlignment(self.inputbox, QtCore.Qt.AlignBottom)
        vertical_layout2.setAlignment(self.confirm, QtCore.Qt.AlignBottom)

        #add horizontal
        horizontal_layout.addWidget(self.webcam)
        horizontal_layout.addLayout(vertical_layout2)
        horizontal_layout.setAlignment(vertical_layout2, QtCore.Qt.AlignTop)

        #add vertical
        vertical_layout.addLayout(horizontal_layout)
        vertical_layout.addWidget(self.subtitle)

        self.setLayout(vertical_layout)

    def setName(self):
        self.vid.name = self.inputbox.text()

    def setSubtitle(self, sub):
        self.subtitle.setText(sub)
        
    def setTemperature(self, temp):
        red = '#EE3333'
        gray = '#AAAAAA'
        green = '#92D050'
        color = gray

        if temp > 38:
            color = red
        elif temp > 34:
            color = green
        
        
        if temp == -1:
            text = '대기중'
        else:
            text = '{:.1f}'.format(temp) + '°C' 

        self.temperature.setStyleSheet("background-color: "+color)
        self.temperature.setText(text)
        self.inputbox.setText('')
        
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    form = Form()
    form.show()
    exit(app.exec_())