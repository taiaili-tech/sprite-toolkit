import { GIFEncoder, quantize, applyPalette } from 'gifenc'

function hasTransparentPixels(pixels) {
  for (let i = 3; i < pixels.length; i += 4) {
    if (pixels[i] < 128) return true
  }
  return false
}

/** Swap palette index 0 with the transparent entry so writeFrame can use transparentIndex: 0 */
function ensureTransparentAtZero(palette, index) {
  const tIdx = palette.findIndex(c => c.length >= 4 && c[3] === 0)
  if (tIdx <= 0) return { palette, index }

  const newPalette = palette.slice()
  ;[newPalette[0], newPalette[tIdx]] = [newPalette[tIdx], newPalette[0]]

  const newIndex = new Uint8Array(index.length)
  for (let i = 0; i < index.length; i++) {
    const idx = index[i]
    newIndex[i] = idx === 0 ? tIdx : idx === tIdx ? 0 : idx
  }
  return { palette: newPalette, index: newIndex }
}

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
    const hasAlpha = hasTransparentPixels(pixels)
    const format = hasAlpha ? 'rgba4444' : 'rgb565'
    const quantizeOpts = hasAlpha
      ? { format: 'rgba4444', oneBitAlpha: 128 }
      : { format: 'rgb565' }

    let palette = quantize(pixels, 256, quantizeOpts)
    let index = applyPalette(pixels, palette, format)

    const frameOpts = { palette, delay, repeat: loopCount }
    if (hasAlpha) {
      ;({ palette, index } = ensureTransparentAtZero(palette, index))
      frameOpts.palette = palette
      frameOpts.transparent = true
      frameOpts.transparentIndex = 0
    }

    encoder.writeFrame(index, width, height, frameOpts)
  }

  encoder.finish()
  const bytes = encoder.bytes()
  return new Blob([bytes], { type: 'image/gif' })
}
