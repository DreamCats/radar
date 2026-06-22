import { toBlob } from "html-to-image";

export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error("复制失败");
  }
}

export async function copyElementAsPng(element: HTMLElement): Promise<void> {
  if (!window.isSecureContext) {
    throw new Error("copy-image:insecure-context");
  }
  if (!navigator.clipboard) {
    throw new Error("copy-image:missing-navigator-clipboard");
  }
  if (!navigator.clipboard.write) {
    throw new Error("copy-image:missing-clipboard-write");
  }
  if (typeof ClipboardItem === "undefined") {
    throw new Error("copy-image:missing-clipboard-item");
  }
  if (typeof ClipboardItem.supports === "function" && !ClipboardItem.supports("image/png")) {
    throw new Error("copy-image:unsupported-image-png");
  }

  const blobPromise = renderElementAsPngBlob(element);
  await navigator.clipboard.write([new ClipboardItem({ "image/png": blobPromise })]);
}

export async function renderElementAsPngBlob(element: HTMLElement): Promise<Blob> {
  const rootStyle = getComputedStyle(document.documentElement);
  const background = rootStyle.getPropertyValue("--color-surface-1").trim() || "#0f1011";
  const paddingX = 16;
  const paddingY = 14;
  const contentWidth = Math.ceil(element.scrollWidth || element.getBoundingClientRect().width);
  const contentHeight = Math.ceil(element.scrollHeight || element.getBoundingClientRect().height);
  const blob = await toBlob(element, {
    backgroundColor: background,
    cacheBust: true,
    height: contentHeight + paddingY * 2,
    pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
    style: {
      background,
      borderRadius: "8px",
      boxSizing: "border-box",
      padding: `${paddingY}px ${paddingX}px`,
      width: `${contentWidth + paddingX * 2}px`,
    },
    width: contentWidth + paddingX * 2,
  });

  if (!blob) {
    throw new Error("生成图片失败");
  }
  return blob;
}
