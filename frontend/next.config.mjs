/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["bpmn-js", "diagram-js", "bpmn-moddle", "moddle", "moddle-xml"],
  async rewrites() {
    const target = process.env.BACKEND_URL || "http://localhost:8002";
    return [{ source: "/api/:path*", destination: `${target}/:path*` }];
  },
};

export default nextConfig;
