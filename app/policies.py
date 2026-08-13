"""Shared safety and data-grounding policies for agent variants."""

OBJECTIVE_DATA_POLICY = (
    "只使用工具返回的数据回答客观事实；不得凭记忆补充比分、日期、排名或统计。"
    "工具没有返回可靠记录时，明确说明暂无数据。"
)

PLAY_BY_PLAY_POLICY = (
    "只有用户明确询问回合、节次、最后几秒或具体比赛事件时才调用 Play-by-Play；"
    "普通比赛分析不主动加载全部回合。"
)
