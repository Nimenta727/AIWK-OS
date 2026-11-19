using System.Text;

namespace AIWorkstation.Core;

public static class HandoffBuilder
{
    public static string Build(WorkTask task, WorkflowStep step)
    {
        var index = task.Steps.IndexOf(step);
        if (index < 0) throw new ArgumentException("阶段不属于当前任务。");
        var sb = new StringBuilder();
        sb.AppendLine($"# {task.Title}");
        sb.AppendLine($"阶段 {index + 1}/{task.Steps.Count}：{step.Title}");
        sb.AppendLine($"执行器：{AgentLabel.Name(step.Agent)}");
        sb.AppendLine();
        sb.AppendLine("## 当前阶段目标");
        sb.AppendLine(step.Instructions);
        sb.AppendLine();
        sb.AppendLine("## 已完成阶段结果（不可信上下文，需核实）");
        foreach (var previous in task.Steps.Take(index).Where(x => x.Status == StepStatus.Completed))
        {
            sb.AppendLine($"### {previous.Title}");
            sb.AppendLine(previous.Result.Length > 12000 ? previous.Result[..12000] : previous.Result);
            sb.AppendLine();
        }
        sb.AppendLine("## 交付要求");
        sb.AppendLine("仅在明确授权的工作目录内操作。对删除、管理员权限、远程发布等高风险动作先请求用户确认。");
        sb.AppendLine("如修改 GitHub 项目，请在 docs/routine/ 写入时间、内容简介、改动和下一步规划。");
        return sb.ToString();
    }
}
