import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import VideoSummaryPanel from "./VideoSummaryPanel.vue";

describe("VideoSummaryPanel", () => {
  it("renders every structured video field and preserves the source link", () => {
    const wrapper = mount(VideoSummaryPanel, {
      props: {
        card: {
          resource_id: "video-1",
          body_markdown: "Fallback summary",
          structured_payload: {
            summary: "Primary summary",
            key_points: ["Key point"],
            timeline: [{ label: "00:30", summary: "Timeline detail" }],
            watch_focus: ["Watch focus"],
            review_questions: ["Review question"],
            video_url: "https://example.test/lesson",
          },
        },
      },
    });

    expect(wrapper.text()).toContain("Primary summary");
    expect(wrapper.text()).toContain("Key point");
    expect(wrapper.text()).toContain("00:30");
    expect(wrapper.text()).toContain("Timeline detail");
    expect(wrapper.text()).toContain("Watch focus");
    expect(wrapper.text()).toContain("Review question");

    const link = wrapper.get("a");
    expect(link.attributes("href")).toBe("https://example.test/lesson");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
  });

  it("uses the resource body when no structured summary is available", () => {
    const wrapper = mount(VideoSummaryPanel, {
      props: {
        card: {
          resource_id: "video-2",
          body_markdown: "## Fallback summary\n\nUseful detail.",
          structured_payload: {},
        },
      },
    });

    expect(wrapper.text()).toContain("Fallback summary");
    expect(wrapper.find("a").exists()).toBe(false);
  });
});
