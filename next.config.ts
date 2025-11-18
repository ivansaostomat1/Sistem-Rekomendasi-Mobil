/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    turbo: false, // turn off to test
  },
};

module.exports = nextConfig;

// next.config.js
module.exports = {
  images: {
    domains: ["localhost", "127.0.0.1"],
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "3000",
        pathname: "/cars/**",
      },
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "3000",
        pathname: "/cars/**",
      }
    ],
  },
};
