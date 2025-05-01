#include <Spinnaker.h>
#include <SpinGenApi/SpinnakerGenApi.h>
#include <opencv2/opencv.hpp>
#include <iostream>
#include <filesystem>
#include <thread>

namespace fs = std::filesystem;
using namespace Spinnaker;
using namespace Spinnaker::GenApi;
using namespace std::chrono_literals;

const std::string SAVE_DIR = "rov_photosphere";
const std::vector<int> ROTATION_ANGLES = {0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330};
const std::vector<int> TILT_ANGLES = {-30, 0, 30};
const std::string STITCHED_IMG = "stitched.jpg";

void create_save_dir() {
    if (!fs::exists(SAVE_DIR)) {
        fs::create_directory(SAVE_DIR);
    }
}

cv::Mat acquire_image(CameraPtr pCam) {
    pCam->BeginAcquisition();

    ImagePtr pResultImage = pCam->GetNextImage();
    if (pResultImage->IsIncomplete()) {
        std::cerr << "Image incomplete." << std::endl;
        pResultImage->Release();
        pCam->EndAcquisition();
        return {};
    }

    // Convert to BGR8 (for OpenCV)
    ImagePtr convertedImage = pResultImage;

    cv::Mat img(convertedImage->GetHeight(), convertedImage->GetWidth(), CV_8UC3, convertedImage->GetData());

    // Copy the image to ensure memory safety
    cv::Mat final_img = img.clone();

    pResultImage->Release();
    pCam->EndAcquisition();

    return final_img;
}

void run_capture() {
    create_save_dir();

    SystemPtr system = System::GetInstance();
    CameraList camList = system->GetCameras();
    if (camList.GetSize() == 0) {
        std::cerr << "No camera detected." << std::endl;
        system->ReleaseInstance();
        return;
    }

    CameraPtr cam = camList.GetByIndex(0);
    cam->Init();

    std::cout << "Start capturing images..." << std::endl;

    for (int tilt : TILT_ANGLES) {
        std::cout << "\nSet ROV tilt to " << tilt << "°, then press ENTER.";
        std::cin.ignore();

        for (int yaw : ROTATION_ANGLES) {
            std::cout << "Rotate ROV to yaw " << yaw << "°, then press ENTER to capture.";
            std::cin.ignore();

            cv::Mat img = acquire_image(cam);
            if (!img.empty()) {
                std::string filename = SAVE_DIR + "/tilt" + std::to_string(tilt) + "_yaw" + std::to_string(yaw) + ".jpg";
                cv::imwrite(filename, img);
                std::cout << "Saved " << filename << std::endl;
            }

            std::this_thread::sleep_for(500ms);
        }
    }

    cam->DeInit();
    cam = nullptr;
    camList.Clear();
    system->ReleaseInstance();

    std::cout << "\nCapture complete." << std::endl;
}

cv::Mat stitch_photosphere() {
    std::vector<cv::Mat> rows;

    for (int tilt : TILT_ANGLES) {
        std::vector<cv::Mat> row_images;

        for (int yaw : ROTATION_ANGLES) {
            std::string filename = SAVE_DIR + "/tilt" + std::to_string(tilt) + "_yaw" + std::to_string(yaw) + ".jpg";
            if (fs::exists(filename)) {
                cv::Mat img = cv::imread(filename);
                if (!img.empty()) {
                    row_images.push_back(img);
                }
            }
        }

        if (!row_images.empty()) {
            cv::Mat row;
            cv::hconcat(row_images, row);
            rows.push_back(row);
        }
    }

    if (!rows.empty()) {
        cv::Mat final_img;
        cv::vconcat(rows, final_img);
        cv::imwrite(STITCHED_IMG, final_img);
        std::cout << "Stitched image saved as " << STITCHED_IMG << std::endl;
        return final_img;
    }

    std::cerr << "No images found to stitch." << std::endl;
    return {};
}

void view_photosphere(cv::Mat img) {
    std::cout << "Opening photosphere viewer (drag with mouse)...\nPress ESC to exit." << std::endl;

    int offset = 0;
    cv::namedWindow("Photosphere", cv::WINDOW_NORMAL);
    cv::setMouseCallback("Photosphere", [](int event, int x, int, int, void* userdata) {
        if (event == cv::EVENT_MOUSEMOVE) {
            int* offset = static_cast<int*>(userdata);
            *offset = x;
        }
    }, &offset);

    while (true) {
        cv::Mat view;
        int rolled_offset = offset % img.cols;
        cv::hconcat(img(cv::Rect(rolled_offset, 0, img.cols - rolled_offset, img.rows)),
                    img(cv::Rect(0, 0, rolled_offset, img.rows)), view);

        cv::imshow("Photosphere", view);
        if (cv::waitKey(20) == 27) break;
    }

    cv::destroyAllWindows();
}

int main() {
    run_capture();
    cv::Mat stitched = stitch_photosphere();
    if (!stitched.empty()) {
        view_photosphere(stitched);
    }
    return 0;
}
