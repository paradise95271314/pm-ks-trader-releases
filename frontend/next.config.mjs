const desktopBuild = process.env.DESKTOP_BUILD === "1"

const nextConfig = {
  output: desktopBuild ? "export" : "standalone",
  images: { unoptimized: true },
  allowedDevOrigins: ["localhost"],
  ...(desktopBuild ? {} : {
    async rewrites() {
      return [{
        source: "/api/:path*",
        destination: (process.env.BACKEND_URL || "http://localhost:8765") + "/:path*",
      }]
    },
  }),
}

export default nextConfig
