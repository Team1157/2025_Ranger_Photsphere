// sharkview.cpp
// Qt + OpenCV + Spinnaker based application with Photosphere and Measurement (no shot the measurement works)

#include <QApplication>
#include <QMainWindow>
#include <QPushButton>
#include <QLabel>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QStackedWidget>
#include <QGraphicsView>
#include <QGraphicsScene>
#include <QMouseEvent>
#include <QPixmap>
#include <QPainter>
#include <QFileDialog>
#include <QComboBox>
#include <opencv2/opencv.hpp>
#include <Spinnaker.h>
#include <SpinGenApi/SpinnakerGenApi.h>
#include <cmath>
#include <vector>

using namespace Spinnaker;
using namespace Spinnaker::GenApi;

class CaptureWidget : public QWidget {
    Q_OBJECT

public:
    CaptureWidget(QWidget *parent = nullptr) : QWidget(parent), currentIndex(0) {
        QVBoxLayout *layout = new QVBoxLayout(this);

        cameraSelector = new QComboBox;
        layout->addWidget(new QLabel("Select Camera:"));
        layout->addWidget(cameraSelector);

        imageView = new QLabel("Camera View");
        imageView->setMinimumSize(640, 480);
        imageView->setStyleSheet("background-color: black;");

        instruction = new QLabel("Instructions");

        QPushButton *captureBtn = new QPushButton("Capture Image");
        QPushButton *nextBtn = new QPushButton("Next Direction");
        QPushButton *stitchBtn = new QPushButton("Stitch Photosphere");

        connect(captureBtn, &QPushButton::clicked, this, &CaptureWidget::captureImage);
        connect(nextBtn, &QPushButton::clicked, this, &CaptureWidget::nextPose);
        connect(stitchBtn, &QPushButton::clicked, this, &CaptureWidget::stitchPhotosphere);

        layout->addWidget(imageView);
        layout->addWidget(instruction);
        layout->addWidget(captureBtn);
        layout->addWidget(nextBtn);
        layout->addWidget(stitchBtn);

        poses = {
            {0, -30}, {30, -30}, {60, -30}, {90, -30}, {120, -30}, {150, -30},
            {0, 0}, {30, 0}, {60, 0}, {90, 0}, {120, 0}, {150, 0},
            {0, 30}, {30, 30}, {60, 30}, {90, 30}, {120, 30}, {150, 30}
        };

        system = System::GetInstance();
        camList = system->GetCameras();
        for (unsigned int i = 0; i < camList.GetSize(); ++i) {
            CameraPtr c = camList.GetByIndex(i);
            INodeMap& nodeMapTLDevice = c->GetTLDeviceNodeMap();
            CStringPtr ptrSerial = nodeMapTLDevice.GetNode("DeviceSerialNumber");
            QString serial = (IsAvailable(ptrSerial) && IsReadable(ptrSerial)) ? QString::fromStdString(ptrSerial->GetValue().c_str()) : QString("Camera %1").arg(i);
            cameraSelector->addItem(serial, QVariant::fromValue<int>(i));
        }

        connect(cameraSelector, QOverload<int>::of(&QComboBox::currentIndexChanged),
                this, &CaptureWidget::changeCamera);

        if (camList.GetSize() > 0) {
            cam = camList.GetByIndex(0);
            cam->Init();
        }

        updateInstruction();
    }

    ~CaptureWidget() {
        if (cam && cam->IsInitialized()) {
            cam->DeInit();
            delete cam;
        }
        camList.Clear();
        system->ReleaseInstance();
    }

private:
    struct Pose { int yaw, tilt; };
    QLabel *imageView;
    QLabel *instruction;
    QComboBox *cameraSelector;
    std::vector<Pose> poses;
    int currentIndex;
    SystemPtr system;
    CameraList camList;
    CameraPtr cam;

    void updateInstruction() {
        if (currentIndex < poses.size()) {
            Pose p = poses[currentIndex];
            instruction->setText(QString("Tilt %1°, Rotate to %2°").arg(p.tilt).arg(p.yaw));
            QPixmap pixmap(640, 480);
            pixmap.fill(Qt::black);
            QPainter painter(&pixmap);
            painter.setPen(Qt::yellow);
            QPoint center(320, 240);
            double angle_rad = p.yaw * M_PI / 180.0;
            QPoint arrow_end(center.x() + 100 * std::cos(angle_rad), center.y() - 100 * std::sin(angle_rad));
            painter.drawLine(center, arrow_end);
            imageView->setPixmap(pixmap);
        } else {
            instruction->setText("Capture complete.");
        }
    }

    void changeCamera(int index) {
        if (cam && cam->IsInitialized()) {
            cam->DeInit();
            cam = nullptr;
        }
        if (index >= 0 && index < static_cast<int>(camList.GetSize())) {
            cam = camList.GetByIndex(index);
            cam->Init();
            instruction->setText(QString("Switched to camera %1").arg(index));
        }
    }

    void captureImage() {
        if (!cam || !cam->IsInitialized()) return;

        cam->BeginAcquisition();

        ImagePtr pResultImage = cam->GetNextImage();
	if (!pResultImage->IsIncomplete()) {
	    const unsigned char* rawData = (const unsigned char*)pResultImage->GetData();
	    int width = pResultImage->GetWidth();
	    int height = pResultImage->GetHeight();
	    cv::Mat img(height, width, CV_8UC3, (void*)rawData);
	    // Now you can use the OpenCV image processing functions
	}
 	else {
            instruction->setText("Image incomplete");
        }

        pResultImage->Release();
        cam->EndAcquisition();
    }

    void nextPose() {
        if (++currentIndex < poses.size()) {
            updateInstruction();
        } else {
            instruction->setText("Capture sequence finished.");
        }
    }

    void stitchPhotosphere() {
        std::vector<cv::Mat> rows;
        for (int tilt : {-30, 0, 30}) {
            std::vector<cv::Mat> row_imgs;
            for (int yaw : {0, 30, 60, 90, 120, 150}) {
                QString fname = QString("capture_tilt%1_yaw%2.jpg").arg(tilt).arg(yaw);
                cv::Mat img = cv::imread(fname.toStdString());
                if (!img.empty()) row_imgs.push_back(img);
            }
        }
        if (!rows.empty()) {
            cv::Mat final_img;
            cv::vconcat(rows, final_img);
            QString output = QFileDialog::getSaveFileName(this, "Save Stitched Image", "stitched.jpg", "Images (*.jpg)");
            if (!output.isEmpty()) {
                cv::imwrite(output.toStdString(), final_img);
            }
        }
    }
};

class MeasureWidget : public QLabel {
    Q_OBJECT

public:
    MeasureWidget(QWidget *parent = nullptr) : QLabel(parent), selecting(false) {
        setFixedSize(640, 480);
        setStyleSheet("background-color: black;");
        setMouseTracking(true);
        img = cv::imread("sample_scene.jpg");
        if (!img.empty()) drawImage();
    }

protected:
    void mousePressEvent(QMouseEvent *event) override {
        if (!selecting) {
            pt1 = event->pos(); selecting = true;
        } else {
            pt2 = event->pos(); selecting = false;
            double px_dist = std::hypot(pt1.x() - pt2.x(), pt1.y() - pt2.y());
            double mm_per_px = 0.264; // Use calibration later
            double real_dist = px_dist * mm_per_px;
            drawImage();
            QPainter painter(&pixmap);
            painter.setPen(Qt::green);
            painter.drawLine(pt1, pt2);
            painter.drawText(pt2, QString("%1 mm").arg(real_dist, 0, 'f', 2));
            setPixmap(pixmap);
        }
    }

private:
    cv::Mat img;
    QPixmap pixmap;
    QPoint pt1, pt2;
    bool selecting;

    void drawImage() {
        if (!img.empty()) {
            QImage qimg(img.data, img.cols, img.rows, img.step, QImage::Format_BGR888);
            pixmap = QPixmap::fromImage(qimg).scaled(size(), Qt::KeepAspectRatio);
            setPixmap(pixmap);
        }
    }
};

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow() {
        QWidget *central = new QWidget;
        QVBoxLayout *mainLayout = new QVBoxLayout(central);

        QHBoxLayout *topButtons = new QHBoxLayout;
        QPushButton *photosphereBtn = new QPushButton("Photosphere Mode");
        QPushButton *measureBtn = new QPushButton("Measurements Mode");
        topButtons->addWidget(photosphereBtn);
        topButtons->addWidget(measureBtn);

        stack = new QStackedWidget;
        stack->addWidget(new CaptureWidget);
        stack->addWidget(new MeasureWidget);

        connect(photosphereBtn, &QPushButton::clicked, [this]() { stack->setCurrentIndex(0); });
        connect(measureBtn, &QPushButton::clicked, [this]() { stack->setCurrentIndex(1); });

        mainLayout->addLayout(topButtons);
        mainLayout->addWidget(stack);
        setCentralWidget(central);
    }

private:
    QStackedWidget *stack;
};

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    MainWindow w;
    w.show();
    return app.exec();
}

#include "sharkview.moc"
