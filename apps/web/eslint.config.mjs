import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTs,
  { ignores: [".next/**", "next-env.d.ts", "playwright-report/**", "test-results/**", "public/vendor/**"] }, // vendor: copied third-party build output
];

export default config;
