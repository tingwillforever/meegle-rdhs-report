import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const basePath = process.env.RDHS_BASE_PATH?.replace(/\/$/, "") ?? "";

export const metadata: Metadata = {
  title: "CBG RDHS运营报告",
  description: "消费者BG RDHS 月度运营报告、趋势分析与产品治理下钻。",
  icons: {
    icon: [{ url: `${basePath}/favicon.png`, type: "image/png", sizes: "96x96" }],
    shortcut: `${basePath}/favicon.png`,
  },
  openGraph: {
    title: "CBG RDHS运营报告",
    description: "消费者BG RDHS 月度运营报告、趋势分析与产品治理下钻。",
    type: "website",
    locale: "zh_CN",
    images: [{ url: `${basePath}/og.png`, width: 1200, height: 630, alt: "RDHS 产研过程效能运营报告" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "CBG RDHS运营报告",
    description: "消费者BG RDHS 月度运营报告、趋势分析与产品治理下钻。",
    images: [`${basePath}/og.png`],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
