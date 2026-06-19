export interface ModelOption {
  value: string;   // "provider:model" format
  label: string;   // display name
}

export interface ModelGroup {
  label: string;
  options: ModelOption[];
}

export const MODEL_GROUPS: ModelGroup[] = [
  {
    label: "OpenAI",
    options: [
      { value: "openai:gpt-4o-mini", label: "gpt-4o-mini" },
      { value: "openai:gpt-4o", label: "gpt-4o" },
    ],
  },
  {
    label: "LM Studio (Local)",
    options: [
      { value: "lmstudio:meta-llama-3.1-8b-instruct", label: "Llama 3.1 8B" },
      // { value: "lmstudio:qwen/qwen3.6-35b-a3b", label: "Qwen 3.6 35B" },
      { value: "lmstudio:gemma-2-9b-it", label: "Gemma 2 9B" },
    ],
  },
];

export const DEFAULT_MODEL = "openai:gpt-4o-mini";
