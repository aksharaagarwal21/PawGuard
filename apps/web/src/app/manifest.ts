import type { MetadataRoute } from "next";

/** Installable app metadata. Installing does not enable offline storage; that is a separate, explicit choice. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "PawGuard 360",
    short_name: "PawGuard",
    description: "Community animal vaccination records and field work.",
    start_url: "/en/app",
    scope: "/",
    display: "standalone",
    background_color: "#f7f8f3",
    theme_color: "#205c4f",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
