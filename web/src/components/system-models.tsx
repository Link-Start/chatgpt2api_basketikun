"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent } from "@/components/ui/card";
import { fetchModels, type Model } from "@/lib/api";
import { cn } from "@/lib/utils";

type SystemModelsProps = {
  variant?: "card" | "inline";
  title?: string;
  description?: string;
  className?: string;
};

function ModelChips({ models, isLoading }: { models: Model[]; isLoading: boolean }) {
  if (models.length > 0) {
    return (
      <div className="flex flex-wrap gap-2">
        {models.map((model) => (
          <button
            key={model.id}
            type="button"
            className="inline-flex cursor-pointer items-center rounded-full border border-stone-200 bg-white px-2.5 py-1 text-xs font-medium text-stone-700 transition hover:border-stone-300 hover:bg-stone-50"
            onClick={() => {
              void navigator.clipboard.writeText(model.id);
              toast.success("模型名已复制");
            }}
            title={`点击复制 ${model.id}`}
          >
            <img src="/openai.svg" alt="" aria-hidden="true" className="mr-1.5 size-3.5 shrink-0" />
            {model.id}
          </button>
        ))}
      </div>
    );
  }

  return (
    <span className="text-sm text-stone-400">
      {isLoading ? "正在加载模型列表..." : "当前暂无可用模型"}
    </span>
  );
}

export function SystemModels({
  variant = "card",
  title = "系统可用模型",
  description,
  className,
}: SystemModelsProps) {
  const [models, setModels] = useState<Model[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const loadModels = async () => {
      setIsLoading(true);
      try {
        const data = await fetchModels();
        if (active) {
          setModels(Array.isArray(data.data) ? data.data : []);
        }
      } catch (error) {
        if (active) {
          toast.error(error instanceof Error ? error.message : "加载模型列表失败");
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    void loadModels();

    return () => {
      active = false;
    };
  }, []);

  const content = (
    <div className={cn("space-y-2", className)}>
      <div>
        <div className="text-sm font-medium text-stone-700">
          {title}
          <span className="ml-1 text-stone-400">({models.length})</span>
        </div>
        {description ? <div className="mt-1 text-xs text-stone-500">{description}</div> : null}
      </div>
      <ModelChips models={models} isLoading={isLoading} />
    </div>
  );

  if (variant === "inline") {
    return content;
  }

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="p-4">{content}</CardContent>
    </Card>
  );
}
