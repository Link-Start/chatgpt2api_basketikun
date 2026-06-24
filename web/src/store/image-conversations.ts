"use client";

import type { ImageModel } from "@/lib/api";

export type ImageConversationMode = "generate" | "edit";

export type StoredReferenceImage = {
  name: string;
  type: string;
  dataUrl?: string;
  url?: string;
};

export type StoredImage = {
  id: string;
  taskId?: string;
  status?: "loading" | "success" | "error";
  taskStatus?: "queued" | "running";
  progress?: string;
  b64_json?: string;
  url?: string;
  revised_prompt?: string;
  error?: string;
  startTime?: number;
  elapsedSecs?: number;
  elapsedUpdatedAt?: number;
  durationMs?: number;
};

export type ImageTurnStatus = "queued" | "generating" | "success" | "error";

export type ImageTurn = {
  id: string;
  prompt: string;
  model: ImageModel;
  mode: ImageConversationMode;
  referenceImages: StoredReferenceImage[];
  count: number;
  size: string;
  ratio: string;
  tier: string;
  quality: string;
  images: StoredImage[];
  createdAt: string;
  status: ImageTurnStatus;
  error?: string;
};

export type ImageConversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  turns: ImageTurn[];
};

export type ImageConversationStats = {
  queued: number;
  running: number;
};

export function getImageConversationStats(conversation: ImageConversation | null): ImageConversationStats {
  if (!conversation) {
    return { queued: 0, running: 0 };
  }

  return conversation.turns.reduce(
    (acc, turn) => {
      if (turn.status === "queued") {
        acc.queued += 1;
      } else if (turn.status === "generating") {
        acc.running += 1;
      }
      return acc;
    },
    { queued: 0, running: 0 },
  );
}
