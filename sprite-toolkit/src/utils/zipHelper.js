import JSZip from 'jszip'

/**
 * 打包多个文件并触发浏览器下载
 * @param {Array<{name: string, blob: Blob}>} files
 * @param {string} zipName
 */
export async function downloadAsZip(files, zipName) {
  const zip = new JSZip()
  for (const { name, blob } of files) {
    zip.file(name, blob)
  }
  const content = await zip.generateAsync({ type: 'blob' })
  triggerDownload(content, zipName)
}

/**
 * 触发浏览器下载单个 Blob
 */
export function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
