cmake_minimum_required(VERSION 3.14)
project(sharkview)

set(CMAKE_CXX_STANDARD 17)

# Qt
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt5 REQUIRED COMPONENTS Widgets)

# OpenCV
find_package(OpenCV REQUIRED)

# Spinnaker (update the path if not installed globally)
set(SPINNAKER_ROOT "/opt/spinnaker")  # or "C:/Program Files/FLIR Systems/Spinnaker"
include_directories(${SPINNAKER_ROOT}/include)
link_directories(${SPINNAKER_ROOT}/lib)  # or lib for 32-bit

add_executable(sharkview sharkview.cpp)

target_link_libraries(sharkview
    Qt5::Widgets
    ${OpenCV_LIBS}
    Spinnaker
)
