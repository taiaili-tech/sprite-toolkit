/**
 * 从 ImageBitmap 或 HTMLImageElement 裁出一个矩形区域，返回 PNG Blob
 */
export function cropToBlob(source, x, y, w, h) {
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  ctx.drawImage(source, x, y, w, h, 0, 0, w, h)
  return new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
}

/**
 * 从 ImageData 裁出一个矩形区域，返回新的 ImageData
 */
export function cropImageData(imageData, srcWidth, x, y, w, h) {
  const canvas = document.createElement('canvas')
  canvas.width = srcWidth
  canvas.height = imageData.height
  const ctx = canvas.getContext('2d')
  ctx.putImageData(imageData, 0, 0)

  const out = document.createElement('canvas')
  out.width = w
  out.height = h
  const outCtx = out.getContext('2d')
  outCtx.drawImage(canvas, x, y, w, h, 0, 0, w, h)
  return outCtx.getImageData(0, 0, w, h)
}

/**
 * 将 File / Blob 转为 HTMLImageElement
 */
export function fileToImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = (e) => { URL.revokeObjectURL(url); reject(e) }
    img.src = url
  })
}

/**
 * 将 File 读取为 ArrayBuffer
 */
export function fileToBuffer(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target.result)
    reader.onerror = reject
    reader.readAsArrayBuffer(file)
  })
}
