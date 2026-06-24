import { GIFEncoder, quantize, applyPalette } from 'gifenc'

/**
 * 将帧数组编码为 GIF Blob
 * @param {Array<{imageData: ImageData, delay: number}>} frames
 * @param {number} width
 * @param {number} height
 * @param {number} loopCount - 0 = 无限循环
 * @returns {Blob}
 */
export function encodeGif(frames, width, height, loopCount = 0) {
  const encoder = GIFEncoder()

  for (const { imageData, delay } of frames) {
    const pixels = imageData.data
    const palette = quantize(pixels, 256, { format: 'rgba4444' })
    const index = applyPalette(pixels, palette, 'rgba4444')

    encoder.writeFrame(index, width, height, {
      palette,
      delay,
      repeat: loopCount,
    })
  }

  encoder.finish()
  const bytes = encoder.bytes()
  return new Blob([bytes], { type: 'image/gif' })
}
