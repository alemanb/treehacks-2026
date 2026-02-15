import sys
import os
import configparser
import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst
import pyds  # The library we installed earlier


# --- THE PROBE FUNCTION (The "Tap" into the pipe) ---
def osd_sink_pad_buffer_probe(pad, info, u_data):
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    # Access the metadata attached by YOLO
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list

    while l_frame is not None:
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        l_obj = frame_meta.obj_meta_list

        while l_obj is not None:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)

            # THE MAGIC PRINT LINE
            print(
                f"DETECTED: {obj_meta.obj_label} | Conf: {obj_meta.confidence:.2f} | BBox: {int(obj_meta.rect_params.left)}, {int(obj_meta.rect_params.top)}"
            )

            l_obj = l_obj.next
        l_frame = l_frame.next
    return Gst.PadProbeReturn.OK


# --- THE PIPELINE SETUP ---
def main():
    Gst.init(None)
    pipeline = Gst.Pipeline()

    # Console-only pipeline:
    # - Run YOLO inference
    # - Print detections (pad probe)
    # - No file output, no display window
    #
    # We still read `deepstream_app_config.txt` for source/streammux/primary-gie properties
    # where they map directly to element properties.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_cfg_path = os.path.join(script_dir, "deepstream_app_config.txt")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str  # keep keys as-is (DeepStream uses hyphenated names)
    if os.path.exists(app_cfg_path):
        cfg.read(app_cfg_path)

    def _cfg_get(section: str, key: str, fallback=None):
        try:
            return cfg.get(section, key)
        except Exception:
            return fallback

    def _cfg_getint(section: str, key: str, fallback=None):
        try:
            return cfg.getint(section, key)
        except Exception:
            return fallback

    def _safe_set(el, prop: str, value):
        try:
            if value is not None:
                el.set_property(prop, value)
        except Exception as e:
            # Keep running even if some DeepStream-app-only properties don't exist here.
            print(f"WARNING: could not set {el.get_name()}.{prop}={value!r}: {e}")

    # 1. Create Elements (The LEGO bricks)
    source = Gst.ElementFactory.make("v4l2src", "usb-cam")
    cam_node = _cfg_getint("source0", "camera-v4l2-dev-node", 0)
    source.set_property("device", f"/dev/video{cam_node}")  # Match [source0]

    vidconv = Gst.ElementFactory.make("nvvideoconvert", "converter")
    caps = Gst.ElementFactory.make("capsfilter", "filter")

    cam_w = _cfg_getint("source0", "camera-width", 1280)
    cam_h = _cfg_getint("source0", "camera-height", 720)
    fps_n = _cfg_getint("source0", "camera-fps-n", 5)
    fps_d = _cfg_getint("source0", "camera-fps-d", 1)

    # Demand NVMM memory and NV12 format
    caps.set_property(
        "caps",
        Gst.Caps.from_string(
            f"video/x-raw(memory:NVMM), format=NV12, width={cam_w}, height={cam_h}, framerate={fps_n}/{fps_d}"
        ),
    )

    muxer = Gst.ElementFactory.make("nvstreammux", "muxer")
    _safe_set(muxer, "gpu-id", _cfg_getint("streammux", "gpu-id", 0))
    _safe_set(muxer, "live-source", bool(_cfg_getint("streammux", "live-source", 1)))
    _safe_set(muxer, "batch-size", _cfg_getint("streammux", "batch-size", 1))
    _safe_set(
        muxer,
        "batched-push-timeout",
        _cfg_getint("streammux", "batched-push-timeout", 40000),
    )
    _safe_set(muxer, "width", _cfg_getint("streammux", "width", 1920))
    _safe_set(muxer, "height", _cfg_getint("streammux", "height", 1080))
    _safe_set(
        muxer, "enable-padding", bool(_cfg_getint("streammux", "enable-padding", 0))
    )
    _safe_set(
        muxer, "nvbuf-memory-type", _cfg_getint("streammux", "nvbuf-memory-type", 0)
    )

    pgie = Gst.ElementFactory.make("nvinfer", "yolo-inference")
    _safe_set(pgie, "gpu-id", _cfg_getint("primary-gie", "gpu-id", 0))
    _safe_set(
        pgie, "nvbuf-memory-type", _cfg_getint("primary-gie", "nvbuf-memory-type", 0)
    )
    gie_cfg = _cfg_get("primary-gie", "config-file", "config_infer_primary_yolo26.txt")
    pgie.set_property("config-file-path", os.path.join(script_dir, gie_cfg))

    # Terminal sink (no rendering, no file output)
    sink = Gst.ElementFactory.make("fakesink", "null-sink")

    # 2. Add elements to pipeline
    for el in [source, vidconv, caps, muxer, pgie, sink]:
        pipeline.add(el)

    # 3. Link them together (The "Chain")
    if not source.link(vidconv):
        sys.exit("ERROR: Could not link source to vidconv")
    if not vidconv.link(caps):
        sys.exit("ERROR: Could not link vidconv to caps")

    # Special link for muxer
    sinkpad = muxer.get_request_pad("sink_0")
    srcpad = caps.get_static_pad("src")
    if srcpad.link(sinkpad) != Gst.PadLinkReturn.OK:
        sys.exit(
            "ERROR: Could not link caps to muxer! (Check your caps filter and memory type)"
        )

    if not muxer.link(pgie):
        sys.exit("ERROR: Could not link muxer to pgie")
    if not pgie.link(sink):
        sys.exit("ERROR: Could not link pgie to sink")

    # 4. HOOK UP THE PROBE: after inference (nvinfer src pad)
    pgiesrcpad = pgie.get_static_pad("src")
    pgiesrcpad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    # 5. Start the engine
    loop = GLib.MainLoop()
    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop.run()
    except:
        pass

    pipeline.set_state(Gst.State.NULL)


if __name__ == "__main__":
    main()

