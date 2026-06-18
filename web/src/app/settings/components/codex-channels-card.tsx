"use client";

import { LoaderCircle, Plus, Save, Trash2, Workflow } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { useSettingsStore } from "../store";

const upstreamModels = ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"];

export function CodexChannelsCard() {
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const addCodexChannel = useSettingsStore((state) => state.addCodexChannel);
  const updateCodexChannel = useSettingsStore((state) => state.updateCodexChannel);
  const deleteCodexChannel = useSettingsStore((state) => state.deleteCodexChannel);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  if (isLoadingConfig || !config?.codex_channels) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  const channels = config.codex_channels.channels || [];

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold text-stone-900">
              <Workflow className="size-5 text-stone-500" />
              Codex 渠道
            </div>
            <p className="mt-1 text-xs leading-6 text-stone-500">
              可接入中转站 API，使用 gpt-5.5 / gpt-5.4 / gpt-5.4-mini 作为上游模型，通过 Codex 工具调用生图。
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
            onClick={addCodexChannel}
          >
            <Plus className="size-4" />
            添加渠道
          </Button>
        </div>

        <div className="space-y-4">
          {channels.length === 0 ? (
            <div className="rounded-xl border border-dashed border-stone-300 bg-stone-50 px-4 py-8 text-center text-sm text-stone-500">
              暂无渠道。
            </div>
          ) : null}
          {channels.map((channel) => (
            <div key={channel.id} className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <label className="flex items-center gap-3 text-sm text-stone-700">
                  <Checkbox
                    checked={Boolean(channel.enabled)}
                    onCheckedChange={(checked) => updateCodexChannel(channel.id, { enabled: Boolean(checked) })}
                  />
                  启用渠道
                </label>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-rose-200 bg-white px-3 text-rose-700 hover:bg-rose-50"
                  onClick={() => deleteCodexChannel(channel.id)}
                >
                  <Trash2 className="size-4" />
                  删除
                </Button>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">渠道名称</label>
                  <Input
                    value={channel.name}
                    onChange={(event) => updateCodexChannel(channel.id, { name: event.target.value })}
                    placeholder="例如 备用渠道"
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">Base URL</label>
                  <Input
                    value={channel.base_url}
                    onChange={(event) => updateCodexChannel(channel.id, { base_url: event.target.value })}
                    placeholder="https://api.example.com/v1"
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">API Key</label>
                  <Input
                    type="password"
                    value={channel.api_key}
                    onChange={(event) => updateCodexChannel(channel.id, { api_key: event.target.value })}
                    placeholder="sk-..."
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">上游模型</label>
                  <Select
                    value={String(channel.upstream_model || "gpt-5.5")}
                    onValueChange={(value) => updateCodexChannel(channel.id, { upstream_model: value })}
                  >
                    <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {upstreamModels.map((model) => (
                        <SelectItem key={model} value={model}>{model}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">模型前缀</label>
                  <Input
                    value={channel.model_prefix}
                    onChange={(event) => updateCodexChannel(channel.id, { model_prefix: event.target.value })}
                    placeholder="例如 proxy"
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">映射后模型</label>
                  <Input
                    value={channel.mapped_model || ""}
                    readOnly
                    placeholder="前缀-gpt-image-2"
                    className="h-10 rounded-xl border-stone-200 bg-stone-50 text-stone-700"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <Button className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800" onClick={() => void saveConfig()} disabled={isSavingConfig}>
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            保存
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
