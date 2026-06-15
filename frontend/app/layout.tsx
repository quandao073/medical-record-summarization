import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tóm tắt bệnh án thông minh",
  description: "Hỗ trợ bác sĩ đọc nhanh hồ sơ bệnh nhân",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
