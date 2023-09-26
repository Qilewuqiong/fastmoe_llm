#include <unordered_map>
#include <mutex>
#include <cassert>
#include <thread>
#include <iostream>
#include <c10/cuda/CUDAGuard.h>
#include <ATen/cuda/CUDAContext.h>

#include "fastermoe/status.h"
#include "stream_manager.h"

#define SMGR_N_STREAMS 16


cudaStream_t CudaStreamManager::stream(size_t idx) {
    if (this->use_default) {
        return c10::cuda::getCurrentCUDAStream().stream();
    }
    return this->streams[idx % SMGR_N_STREAMS];
}

cublasHandle_t CudaStreamManager::handle(size_t idx) {
    if (this->use_default) {
        return at::cuda::getCurrentCUDABlasHandle();
    }
    return this->handles[idx % SMGR_N_STREAMS];
}


void CudaStreamManager::sync(int idx) {
    if (this->use_default) {
        return;
    }
    for (int i = 0; i < idx && i < SMGR_N_STREAMS; ++i) {
        cudaStreamSynchronize(streams[i]);
    }
}

void CudaStreamManager::setup(const int device) {
#ifdef FMOE_USE_NCCL
    this->ncclgood = 0;
#endif
    this->device = device;
    checkCudaErrors(cudaSetDevice(device));
    streams = new cudaStream_t[SMGR_N_STREAMS];
    handles = new cublasHandle_t[SMGR_N_STREAMS];
    for (size_t i = 0; i < SMGR_N_STREAMS; ++i) {
        checkCudaErrors(cudaStreamCreate(streams + i));
        checkCudaErrors(cublasCreate(handles + i));
        cublasSetStream(handles[i], streams[i]);
    }
}

void CudaStreamManager::destroy() {
    for (size_t i = 0; i < SMGR_N_STREAMS; ++i) {
        checkCudaErrors(cudaStreamDestroy(streams[i]));
        checkCudaErrors(cublasDestroy(handles[i]));
    }
    delete[] streams;
    delete[] handles;
}

std::unordered_map<int, CudaStreamManager*> smgrs;
std::mutex smgr_mtx;

CudaStreamManager* getCudaStreamManager(const int device) {
    std::pair<std::unordered_map<int, CudaStreamManager *>::iterator, bool > ret;
    auto it = smgrs.find(device);
    if (it == smgrs.end()) {
        smgr_mtx.lock();
        it = smgrs.find(device);
        if (it == smgrs.end()) {
            auto smgr = new CudaStreamManager(device);
            ret = smgrs.emplace(device, smgr);
            smgr_mtx.unlock();

            return smgr;
        } else {
            smgr_mtx.unlock();
        }
    }
    return it->second;
}

