import { parseGIF, decompressFrames } from 'gifuct-js'

/**
 * Extract loop count from NETSCAPE2.0 application extension (0 = infinite).
 */
function getLoopCount(gif) {
  for (const frame of gif.frames) {
    if (frame.application?.id === 'NETSCAPE2.0') {
      const blocks = frame.application.blocks
      if (blocks && blocks.length >= 3) {
        return blocks[1] | (blocks[2] << 8)
      }
    }
  }
  return 0
}

/**
 * 解码 GIF ArrayBuffer，返回帧信息数组
 * @param {ArrayBuffer} buffer
 * @returns {Promise<{frames: DecodedFrame[], width: number, height: number, loopCount: number}>}
 *
 * DecodedFrame: { imageData: ImageData, delay: number }
 */
export async function decodeGif(buffer) {
  const arr = new Uint8Array(buffer)
  const gif = parseGIF(arr)
  const frames = decompressFrames(gif, true)

  const width = gif.lsd.width
  const height = gif.lsd.height
  const loopCount = getLoopCount(gif)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')

  const result = []
  for (const frame of frames) {
    const imageData = ctx.createImageData(frame.dims.width, frame.dims.height)
    imageData.data.set(frame.patch)

    ctx.putImageData(imageData, frame.dims.left, frame.dims.top)

    const fullImageData = ctx.getImageData(0, 0, width, height)
    result.push({
      imageData: fullImageData,
      delay: frame.delay || 100,
    })
  }

  return { frames: result, width, height, loopCount }
}
