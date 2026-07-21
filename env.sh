export CUDA_HOME=$CONDA_PREFIX
export PYTHONPATH=$PWD
export WORKING_DIR=$PWD
export HF_HOME=$PWD/.cache/hf
export TRITON_CACHE_DIR=$PWD/.cache/triton
export PIP_CACHE_DIR=$PWD/.cache/pip
export UV_CACHE_DIR=$PWD/.cache/uv
export XDG_DATA_HOME=$PWD/.cache/xdg
export CONDA_PKGS_DIRS=$PWD/.cache/conda
# as the gpu is 5090, set TORCH_CUDA_ARCH_LIST 
export TORCH_CUDA_ARCH_LIST="8.6 9.0 12.0"
export CC=/usr/bin/gcc
export CXX=/usr/bin/g++
export LD_LIBRARY_PATH=$HOME/.mujoco/mujoco210/bin:$CONDA_PREFIX/lib:/usr/lib/nvidia

# check if the conda environment "ada_vla" is activated, if not activate it
if [[ "$CONDA_DEFAULT_ENV" != "ada_vla" ]]; then
    echo "Activating conda environment 'ada_vla'..."
    eval "$(conda shell.bash hook)"
    conda activate ada_vla
else
    echo "Conda environment 'ada_vla' is already activated."
fi