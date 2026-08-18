/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  experimental: {
    serverActions: {
      allowedOrigins: ["*"]
    }
  },
  images: {
    remotePatterns: []
  }
}
