import type { BBox } from "./types";

export function formatBBox(b: BBox | null | undefined): string {
  if (!b) return "—";
  return `${Math.round(b.x)},${Math.round(b.y)} · ${Math.round(b.w)}×${Math.round(b.h)}`;
}

export function formatBBoxLong(b: BBox | null | undefined): string {
  if (!b) return "no bbox";
  const x2 = Math.round(b.x + b.w);
  const y2 = Math.round(b.y + b.h);
  return `top-left (${Math.round(b.x)}, ${Math.round(b.y)}) → bottom-right (${x2}, ${y2}) · ${b.coord_space}`;
}

export async function copyBBox(b: BBox): Promise<boolean> {
  const json = JSON.stringify({
    x: Math.round(b.x),
    y: Math.round(b.y),
    w: Math.round(b.w),
    h: Math.round(b.h),
    x2: Math.round(b.x + b.w),
    y2: Math.round(b.y + b.h),
    page_index: b.page_index,
    coord_space: b.coord_space,
  });
  try {
    await navigator.clipboard.writeText(json);
    return true;
  } catch {
    return false;
  }
}
