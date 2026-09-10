const MAX_IMAGE_DIMENSION = 2048;
const IMAGE_QUALITY = 0.86;
const MAX_VIDEO_BYTES = 80 * 1024 * 1024;
const MAX_VIDEO_SECONDS = 60;

function imageOutputType(file: File): string {
  if (file.type === "image/png" && file.size < 2 * 1024 * 1024) return "image/png";
  return "image/jpeg";
}

export async function optimizeImage(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) return file;

  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_IMAGE_DIMENSION / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));

  if (scale === 1 && file.size <= 2 * 1024 * 1024 && file.type !== "image/heic" && file.type !== "image/heif") {
    bitmap.close();
    return file;
  }

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) {
    bitmap.close();
    return file;
  }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  const type = imageOutputType(file);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, IMAGE_QUALITY));
  if (!blob || blob.size >= file.size) return file;
  return new File([blob], file.name.replace(/\.[^.]+$/, type === "image/png" ? ".png" : ".jpg"), {
    type,
    lastModified: Date.now(),
  });
}

export async function validateVideoForUpload(file: File): Promise<void> {
  if (!file.type.startsWith("video/")) return;
  if (file.size > MAX_VIDEO_BYTES) throw new Error("Video is too large. Choose a video under 80 MB.");

  const url = URL.createObjectURL(file);
  try {
    const duration = await new Promise<number>((resolve, reject) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.onloadedmetadata = () => resolve(video.duration);
      video.onerror = () => reject(new Error("Unable to inspect video metadata."));
      video.src = url;
    });
    if (!Number.isFinite(duration) || duration > MAX_VIDEO_SECONDS) {
      throw new Error("Video must be 60 seconds or shorter.");
    }
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function optimizeMedia(file: File): Promise<File> {
  if (file.type.startsWith("image/")) return optimizeImage(file);
  await validateVideoForUpload(file);
  return file;
}
