"use client";

import dynamic from "next/dynamic";

/** MapLibre is loaded only on this page and only in the browser. */
export const LazyAreaMap = dynamic(() => import("./area-map"), {
  ssr: false,
  loading: () => <div className="h-[22rem] w-full animate-pulse rounded-card bg-divider/40 md:h-[30rem]" aria-hidden />,
});
