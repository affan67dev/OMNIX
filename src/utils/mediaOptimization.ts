const MAX_IMAGE_DIMENSION = 2048;
const MIN_IMAGE_DIMENSION = 720;
const MAX_IMAGE_BYTES = 300 * 1024;
const MAX_VIDEO_BYTES = 80 * 1024 * 1024;
const MAX_VIDEO_SECONDS = 60;
const TARGET_VIDEO_HEIGHT = 720;
const TARGET_VIDEO_BITRATE = 2_500_000;

function imageOutputType(file: File): string {
  // JPEG gives predictable size for photos. Keep small PNGs lossless.
  if (file.type === "image/png" && file.size <= MAX_IMAGE_BYTES) return "image/png";
  return "image/jpeg";
}

function encodeCanvas(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

/**
 * Resize/compress photos before Storage upload. The encoder is iterated until
 * the 300 KiB target is reached or the safe minimum dimensions are reached.
 */
export async function optimizeImage(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) return file;
  if (file.size <= MAX_IMAGE_BYTES && !/image\/(heic|heif)/i.test(file.type)) return file;

  const bitmap = await createImageBitmap(file);
  try {
    let dimension = Math.min(MAX_IMAGE_DIMENSION, Math.max(bitmap.width, bitmap.height));
    const type = imageOutputType(file);
    let best: Blob | null = null;

    for (let pass = 0; pass < 8; pass += 1) {
      const scale = Math.min(1, dimension / Math.max(bitmap.width, bitmap.height));
      const width = Math.max(1, Math.round(bitmap.width * scale));
      const height = Math.max(1, Math.round(bitmap.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d", { alpha: type === "image/png" });
      if (!context) throw new Error("Image encoder is unavailable on this device.");
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.drawImage(bitmap, 0, 0, width, height);

      const quality = Math.max(0.56, 0.88 - pass * 0.045);
      const blob = await encodeCanvas(canvas, type, quality);
      if (!blob) throw new Error("Unable to encode image for upload.");
      best = blob;
      if (blob.size <= MAX_IMAGE_BYTES) {
        return new File([blob], file.name.replace(/\.[^.]+$/, type === "image/png" ? ".png" : ".jpg"), {
          type,
          lastModified: Date.now(),
        });
      }
      dimension = Math.max(MIN_IMAGE_DIMENSION, Math.floor(dimension * 0.82));
      if (dimension === MIN_IMAGE_DIMENSION && pass >= 6) break;
    }

    // A hard client-side budget is preferable to uploading an oversized asset.
    if (best && best.size <= MAX_IMAGE_BYTES) {
      return new File([best], file.name.replace(/\.[^.]+$/, ".jpg"), { type: "image/jpeg", lastModified: Date.now() });
    }
    throw new Error("Image could not be optimized below 300 KB. Choose a simpler image.");
  } finally {
    bitmap.close();
  }
}

async function readVideoMetadata(file: File): Promise<{ duration: number; width: number; height: number }> {
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.onloadedmetadata = () => resolve({ duration: video.duration, width: video.videoWidth, height: video.videoHeight });
      video.onerror = () => reject(new Error("Unable to inspect video metadata."));
      video.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Browser-native short-video transcode. MediaRecorder is used only when the
 * platform supports captureStream; otherwise validation remains authoritative.
 */
export async function optimizeVideo(file: File): Promise<File> {
  if (!file.type.startsWith("video/")) return file;
  const metadata = await readVideoMetadata(file);
  if (!Number.isFinite(metadata.duration) || metadata.duration > MAX_VIDEO_SECONDS) {
    throw new Error("Video must be 60 seconds or shorter.");
  }
  if (file.size <= 12 * 1024 * 1024 && metadata.height <= TARGET_VIDEO_HEIGHT) return file;

  const VideoCtor = window.HTMLVideoElement;
  if (!VideoCtor || typeof MediaRecorder === "undefined") return file;
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.src = URL.createObjectURL(file);
  try {
    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => resolve();
      video.onerror = () => reject(new Error("Unable to prepare video."));
    });
    const scale = Math.min(1, TARGET_VIDEO_HEIGHT / Math.max(1, video.videoHeight));
    const width = Math.max(2, Math.round(video.videoWidth * scale / 2) * 2);
    const height = Math.max(2, Math.round(video.videoHeight * scale / 2) * 2);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx || typeof (video as HTMLVideoElement & { captureStream?: () => MediaStream }).captureStream !== "function") return file;

    const canvasStream = canvas.captureStream(30);
    const sourceStream = (video as HTMLVideoElement & { captureStream: () => MediaStream }).captureStream();
    for (const track of sourceStream.getAudioTracks()) canvasStream.addTrack(track);
    const mimeType = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"].find((type) => MediaRecorder.isTypeSupported(type));
    if (!mimeType) return file;

    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(canvasStream, { mimeType, videoBitsPerSecond: TARGET_VIDEO_BITRATE });
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    const finished = new Promise<Blob>((resolve, reject) => {
      recorder.onerror = () => reject(new Error("Video optimization failed."));
      recorder.onstop = () => resolve(new Blob(chunks, { type: mimeType }));
    });

    const draw = () => {
      if (video.ended) return;
      ctx.drawImage(video, 0, 0, width, height);
      requestAnimationFrame(draw);
    };
    recorder.start(1000);
    draw();
    await video.play();
    await new Promise<void>((resolve) => { video.onended = () => resolve(); });
    if (recorder.state !== "inactive") recorder.stop();
    const blob = await finished;
    if (blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, ".webm"), { type: mimeType, lastModified: Date.now() });
  } finally {
    URL.revokeObjectURL(video.src);
  }
}

export async function validateVideoForUpload(file: File): Promise<void> {
  if (!file.type.startsWith("video/")) return;
  if (file.size > MAX_VIDEO_BYTES) throw new Error("Video is too large. Choose a video under 80 MB.");
  const metadata = await readVideoMetadata(file);
  if (!Number.isFinite(metadata.duration) || metadata.duration > MAX_VIDEO_SECONDS) {
    throw new Error("Video must be 60 seconds or shorter.");
  }
}

export async function optimizeMedia(file: File): Promise<File> {
  if (file.type.startsWith("image/")) return optimizeImage(file);
  if (file.type.startsWith("video/")) {
    await validateVideoForUpload(file);
    return optimizeVideo(file);
  }
  return file;
}
