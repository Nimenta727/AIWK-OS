namespace AIWorkstation.Core;

/// <summary>Pure DAG validation. For legacy tasks GraphMode=false retains sequential ordering.</summary>
public static class WorkflowGraph
{
    public static void Validate(WorkTask task)
    {
        if(!task.GraphMode) return;
        if(task.Steps.Count is < 1 or > 200) throw new InvalidDataException("DAG 阶段数量不合法。");
        var lookup = task.Steps.ToDictionary(x=>x.Id,StringComparer.Ordinal);
        var visited = new Dictionary<string,int>(StringComparer.Ordinal);
        void Visit(string id)
        {
            if(visited.TryGetValue(id,out var status))
            {
                if(status==1) throw new InvalidDataException("DAG 存在依赖环。");
                return;
            }
            visited[id]=1;
            var step = lookup[id];
            if(step.DependsOn is null || step.DependsOn.Count>100 || step.DependsOn.Distinct(StringComparer.Ordinal).Count()!=step.DependsOn.Count)
                throw new InvalidDataException("DAG 依赖无效或重复。");
            foreach(var dependency in step.DependsOn)
            {
                if(!lookup.ContainsKey(dependency) || dependency==id) throw new InvalidDataException("DAG 依赖不存在或自引用。");
                Visit(dependency);
            }
            visited[id]=2;
        }
        foreach(var step in task.Steps) Visit(step.Id);
    }
    public static IReadOnlyList<WorkflowStep> Ready(WorkTask task)
    {
        Validate(task);
        return task.Steps.Where(s=>s.Status==StepStatus.Pending &&
            (!task.GraphMode ? task.Steps.Take(task.Steps.IndexOf(s)).All(p=>p.Status==StepStatus.Completed)
            : s.DependsOn.All(id=>task.Steps.Single(x=>x.Id==id).Status==StepStatus.Completed))).ToArray();
    }
}
