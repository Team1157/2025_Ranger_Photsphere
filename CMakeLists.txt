cmake_minimum_required(VERSION 3.10)
project(ROVPhotosphere)

set(CMAKE_CXX_STANDARD 17)

find_package(OpenCV REQUIRED)
include_directories(${OpenCV_INCLUDE_DIRS})

# Replace with the actual path to your Spinnaker SDK
set(SPINNAKER_INCLUDE_DIR "/opt/spinnaker/include")
set(SPINNAKER_LIB_DIR "/opt/spinnaker/lib")

include_directories(${SPINNAKER_INCLUDE_DIR})
link_directories(${SPINNAKER_LIB_DIR})

add_executable(ROVPhotosphere main.cpp)
target_link_libraries(ROVPhotosphere ${OpenCV_LIBS} Spinnaker)
