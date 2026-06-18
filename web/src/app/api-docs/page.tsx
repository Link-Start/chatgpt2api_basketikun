"use client";

import { LoaderCircle } from "lucide-react";

import { useAuthGuard } from "@/lib/use-auth-guard";
import { ApiDocsCard } from "./components/api-docs-card";

export default function ApiDocsPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);

  if (isCheckingAuth || !session || session.role !== "admin") {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <LoaderCircle className="size-5 animate-spin text-stone-400" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-stone-950 dark:text-stone-50">接口文档</h1>
        <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">查看兼容接口、请求参数和调用示例。</p>
      </div>
      <ApiDocsCard />
    </div>
  );
}
