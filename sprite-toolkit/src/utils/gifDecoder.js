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
    let restoreState = null
    if (frame.disposalType === 3) {
      restoreState = ctx.getImageData(0, 0, width, height)
    }

    const imageData = ctx.createImageData(frame.dims.width, frame.dims.height)
    imageData.data.set(frame.patch)

    // Use drawImage via a temp canvas so transparent pixels don't overwrite
    // existing canvas content (putImageData would zero-out alpha, causing corruption)
    const tmpCanvas = document.createElement('canvas')
    tmpCanvas.width = frame.dims.width
    tmpCanvas.height = frame.dims.height
    tmpCanvas.getContext('2d').putImageData(imageData, 0, 0)
    ctx.drawImage(tmpCanvas, frame.dims.left, frame.dims.top)

    const fullImageData = ctx.getImageData(0, 0, width, height)
    result.push({
      imageData: fullImageData,
      delay: frame.delay || 100,
    })

    const disposal = frame.disposalType ?? 1
    if (disposal === 2) {
      ctx.clearRect(0, 0, width, height)
    } else if (disposal === 3 && restoreState) {
      ctx.putImageData(restoreState, 0, 0)
    }
  }

  return { frames: result, width, height, loopCount }
}
