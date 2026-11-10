import type { Metadata, Viewport } from "next";
import { Atkinson_Hyperlegible_Next, Barlow, Geist_Mono } from "next/font/google";
import "./globals.css";

// One family for the whole product: designed for legibility by low-vision readers, with clear 1/l/I and 0/O.
const atkinson = Atkinson_Hyperlegible_Next({
  variable: "--font-atkinson",
  subsets: ["latin", "latin-ext"],
  display: "swap",
});

// McKinley's own brand face (mckinley.com uses Barlow): wordmark, headings and buttons only. Body text stays Atkinson.
const barlow = Barlow({
  variable: "--font-barlow",
  subsets: ["latin", "latin-ext"],
  weight: ["500", "600", "700"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "McKinley Help (prototype)",
  description: "Prototype leasing and resident assistant for McKinley communities. Made-up data only.",
};

// resizes-content: Android Chrome shrinks the page when the keyboard opens, so the sticky composer stays above it.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  interactiveWidget: "resizes-content",
  themeColor: "#4e6f92",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${atkinson.variable} ${barlow.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-mk-paper text-mk-ink">{children}</body>
    </html>
  );
}
