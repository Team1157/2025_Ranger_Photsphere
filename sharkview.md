## Windows: 
mkdir build-windows
cd build-windows
cmake .. -DCMAKE_TOOLCHAIN_FILE=../toolchain-mingw64.cmake
cmake --build .


## Linux:
mkdir build
cd build
cmake ..
cmake --build .
