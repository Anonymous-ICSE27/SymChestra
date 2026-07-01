FROM ubuntu:16.04

ARG BASE_DIR=/root/symchestra
ARG SYMCHESTRA_GCOV_COPIES=1
ENV SYMCHESTRA_GCOV_COPIES=${SYMCHESTRA_GCOV_COPIES}

EXPOSE 2025

# install requirements
RUN apt-get update && \
    apt-get install -y gdb && \
    apt-get install -yq tzdata && \
    ln -fs /usr/share/zoneinfo/Amercia/New_York /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata 
RUN apt-get -y update
RUN apt-get -y install build-essential curl libcap-dev git cmake libncurses5-dev python3-minimal unzip libtcmalloc-minimal4 libgoogle-perftools-dev libsqlite3-dev doxygen gcc-multilib g++-multilib wget

# install python3.8
RUN apt-get install -y wget build-essential checkinstall  libreadline-gplv2-dev libssl-dev tk-dev libgdbm-dev libc6-dev libbz2-dev libffi-dev zlib1g-dev
WORKDIR /root
RUN wget https://www.python.org/ftp/python/3.8.10/Python-3.8.10.tgz
RUN tar xzf Python-3.8.10.tgz
WORKDIR /root/Python-3.8.10
RUN ./configure --enable-optimizations
RUN make install

RUN apt-get -y install python3-pip
RUN pip3 install --upgrade pip
RUN pip3 install tabulate numpy wllvm scikit-learn matplotlib scipy
RUN apt-get -y install clang-6.0 llvm-6.0 llvm-6.0-dev llvm-6.0-tools
RUN ln -s /usr/bin/clang-6.0 /usr/bin/clang
RUN ln -s /usr/bin/clang++-6.0 /usr/bin/clang++
RUN ln -s /usr/bin/llvm-config-6.0 /usr/bin/llvm-config
RUN ln -s /usr/bin/llvm-link-6.0 /usr/bin/llvm-link


WORKDIR /root

# Install stp solver
RUN apt-get -y install cmake bison flex libboost-all-dev python perl minisat
WORKDIR ${BASE_DIR}
RUN git clone https://github.com/stp/stp.git
WORKDIR ${BASE_DIR}/stp
RUN git checkout tags/2.3.3
RUN mkdir build
WORKDIR ${BASE_DIR}/stp/build
RUN cmake ..
RUN make -j
RUN make install

RUN echo "ulimit -s unlimited" >> /root/.bashrc

# install klee-uclibc
WORKDIR ${BASE_DIR}
RUN git clone https://github.com/klee/klee-uclibc.git
WORKDIR ${BASE_DIR}/klee-uclibc
RUN ./configure --make-llvm-lib
RUN make -j

ADD ./ ${BASE_DIR}
ENV LLVM_COMPILER=clang
ENV FORCE_UNSAFE_CONFIGURE=1

# install klee - featmaker
WORKDIR ${BASE_DIR}/klee_featmaker
RUN mkdir -p build
WORKDIR ${BASE_DIR}/klee_featmaker/build
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_UNIT_TESTS=OFF -DENABLE_SYSTEM_TESTS=OFF -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/klee-uclibc -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config -DLLVMCC=/usr/bin/clang ..
RUN make -j
WORKDIR ${BASE_DIR}/klee_featmaker
RUN if [ -f testing-env.sh ]; then env -i /bin/bash -c 'source testing-env.sh && env > test.env'; else printf 'SHELL=/bin/bash\nTERM=xterm\nLC_ALL=C\nCOLUMNS=80\nPATH=/usr/local/bin:/usr/bin:/bin\nPWD=%s\nSHLVL=1\nTABSIZE=8\nCOLORTERM=gnome-terminal\n' "$PWD/" > test.env; fi

# install klee - klee-ram
WORKDIR ${BASE_DIR}/klee_ram
RUN mkdir -p build
WORKDIR ${BASE_DIR}/klee_ram/build
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_UNIT_TESTS=OFF -DENABLE_SYSTEM_TESTS=OFF -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/klee-uclibc -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config -DLLVMCC=/usr/bin/clang ..
RUN make -j
WORKDIR ${BASE_DIR}/klee_ram
RUN if [ -f testing-env.sh ]; then env -i /bin/bash -c 'source testing-env.sh && env > test.env'; else printf 'SHELL=/bin/bash\nTERM=xterm\nLC_ALL=C\nCOLUMNS=80\nPATH=/usr/local/bin:/usr/bin:/bin\nPWD=%s\nSHLVL=1\nTABSIZE=8\nCOLORTERM=gnome-terminal\n' "$PWD/" > test.env; fi

# install klee - featmaker+homi
WORKDIR ${BASE_DIR}/klee_feathomi
RUN mkdir -p build
WORKDIR ${BASE_DIR}/klee_feathomi/build
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_UNIT_TESTS=OFF -DENABLE_SYSTEM_TESTS=OFF -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/klee-uclibc -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config -DLLVMCC=/usr/bin/clang ..
RUN make -j
WORKDIR ${BASE_DIR}/klee_feathomi
RUN if [ -f testing-env.sh ]; then env -i /bin/bash -c 'source testing-env.sh && env > test.env'; else printf 'SHELL=/bin/bash\nTERM=xterm\nLC_ALL=C\nCOLUMNS=80\nPATH=/usr/local/bin:/usr/bin:/bin\nPWD=%s\nSHLVL=1\nTABSIZE=8\nCOLORTERM=gnome-terminal\n' "$PWD/" > test.env; fi

# install klee - ram+homi
WORKDIR ${BASE_DIR}/klee_ramhomi
RUN mkdir -p build
WORKDIR ${BASE_DIR}/klee_ramhomi/build
RUN cmake -DENABLE_SOLVER_STP=ON -DENABLE_POSIX_RUNTIME=ON -DENABLE_UNIT_TESTS=OFF -DENABLE_SYSTEM_TESTS=OFF -DENABLE_KLEE_UCLIBC=ON -DKLEE_UCLIBC_PATH=${BASE_DIR}/klee-uclibc -DLLVM_CONFIG_BINARY=/usr/bin/llvm-config -DLLVMCC=/usr/bin/clang ..
RUN make -j
WORKDIR ${BASE_DIR}/klee_ramhomi
RUN if [ -f testing-env.sh ]; then env -i /bin/bash -c 'source testing-env.sh && env > test.env'; else printf 'SHELL=/bin/bash\nTERM=xterm\nLC_ALL=C\nCOLUMNS=80\nPATH=/usr/local/bin:/usr/bin:/bin\nPWD=%s\nSHLVL=1\nTABSIZE=8\nCOLORTERM=gnome-terminal\n' "$PWD/" > test.env; fi

# build benchmarks
WORKDIR ${BASE_DIR}/benchmarks
RUN python3 install.py

WORKDIR ${BASE_DIR}
