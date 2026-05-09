"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_WIDTH = 280;
const MIN_WIDTH = 180;
const MAX_WIDTH = 480;
const KEY_STEP = 10;

interface Props {
  children: React.ReactNode;
}

export default function ResizableSidebar({ children }: Props) {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);
  // Mirror width into a ref so onMouseDown never closes over stale state.
  const widthRef = useRef(DEFAULT_WIDTH);
  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  // Stable callback — reads from ref, no width in dep array.
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    startWidth.current = widthRef.current;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setWidth((w) => Math.min(MAX_WIDTH, w + KEY_STEP));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setWidth((w) => Math.max(MIN_WIDTH, w - KEY_STEP));
    } else if (e.key === "Home") {
      e.preventDefault();
      setWidth(MIN_WIDTH);
    } else if (e.key === "End") {
      e.preventDefault();
      setWidth(MAX_WIDTH);
    }
  }, []);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + delta));
      setWidth(next);
    };

    const onMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      // Reset body styles even if dragging was in progress at unmount.
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, []);

  return (
    <>
      <aside
        aria-label="Sidebar"
        className="shrink-0 flex flex-col bg-bg border-r border-frame"
        style={{ width }}
      >
        {children}
      </aside>

      {/* Drag handle — focusable splitter per ARIA APG */}
      <div
        role="separator"
        tabIndex={0}
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        aria-valuenow={width}
        aria-valuemin={MIN_WIDTH}
        aria-valuemax={MAX_WIDTH}
        onMouseDown={onMouseDown}
        onKeyDown={onKeyDown}
        className="w-1 shrink-0 bg-transparent hover:bg-violet-500/40 active:bg-violet-500/60 focus-visible:bg-violet-500/60 focus-visible:outline-none cursor-col-resize transition-colors"
      />
    </>
  );
}
