import os

os.environ["CUDA_MODULE_LOADING"] = "LAZY"

import vapoursynth as vs
from vsdrba import drba_rife

core = vs.core
core.max_cache_size = 2048

user_directory = os.environ['UserDirectory']
if not user_directory:
    raise ValueError("user_directory environment variable not set")
plugins_dir = os.path.join(user_directory, "Documents", "vapoursynth-portable", "vs-plugins")
core.std.LoadPlugin(os.path.join(plugins_dir, "LSMASHSource.dll"))
core.std.LoadPlugin(os.path.join(plugins_dir, "MiscFilters.dll"))

input_video = os.environ.get("VS_SOURCE")
if not input_video:
    raise ValueError("VS_SOURCE environment variable not set")

clip = core.lsmas.LWLibavSource(
    source=input_video,
    cache=0,
    fpsnum=24000, 
    fpsden=1001, 
    prefer_hw=1
)

clip = core.resize.Bicubic(
    clip=clip, 
    format=vs.RGBH, 
    matrix_in_s="709", 
    range_s="limited"
)

clip = drba_rife(
    clip,
    model="4.25",
    scale=2.0,
    sc=True,
    sc_threshold=0.15,
    trt=True,
    trt_optimization_level=5,
    trt_cache_dir=user_directory + "/ConvertedVideos"
)

clip = core.resize.Bicubic(
    clip=clip,
    format=vs.YUV420P10,
    matrix_s="709",
    range_s="limited"
)

clip = core.std.AssumeFPS(
    clip=clip,
    fpsnum=48000,
    fpsden=1001
)

clip.set_output()