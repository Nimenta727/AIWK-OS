"""Import Windows AIWorkstation.Core WorkTask JSON as NON-EXECUTABLE guest history.

Windows WorkflowStep/UnifiedTaskState data is not an authority to execute
Linux tools. All imported stages remain 'unmapped': original status,
plan-revision and artifact evidence are retained as bounded metadata only.
Instructions, token logs, prompts and result contents are never persisted.
"""
import hashlib
import json
import re

GUID=re.compile(r"^[0-9a-fA-F]{32}$")
HEX=re.compile(r"^[0-9a-fA-F]{64}$")
STATUSES=frozenset({"Pending","Running","Completed","Failed","Interrupted"})
AGENTS=frozenset({"ClaudeCode","Codex","Manual"})
MAX_IMPORT_STAGES=32

class WindowsImportError(ValueError):
    pass

def digest(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),ensure_ascii=False
    ).encode("utf-8")).hexdigest()

def guid(value,field):
    if not isinstance(value,str) or not GUID.fullmatch(value):
        raise WindowsImportError("Invalid Windows "+field+" GUID")
    return value.lower()

def text(value,name,maxsize,empty=False):
    if not isinstance(value,str) or len(value)>maxsize or (not empty and not value.strip()):
        raise WindowsImportError("Invalid bounded Windows "+name)
    return value


def optional_guid(value,field):
    return None if value in (None,"") else guid(value,field)

def date_label(value,field):
    """Keep only bounded, timezone-aware Windows timestamps, never local paths."""
    if value in (None,""):
        return None
    if not isinstance(value,str) or len(value)>48:
        raise WindowsImportError("Invalid Windows "+field+" timestamp")
    from datetime import datetime
    try:
        stamp=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise WindowsImportError("Invalid Windows "+field+" timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise WindowsImportError("Windows timestamp must have timezone")
    return value

def summarize_plans(plans):
    output=[]
    for plan in plans:
        path=plan.get("RelativePath","")
        if not isinstance(path,str) or len(path)>512:
            raise WindowsImportError("Invalid Windows plan path metadata")
        output.append({
            "id":optional_guid(plan.get("Id"),"plan revision"),
            "sha256":plan["Sha256"].lower(),
            "linkedAt":date_label(plan.get("LinkedAt"),"plan link"),
            "pathSha256":hashlib.sha256(path.encode("utf-8")).hexdigest() if path else None,
            "contentImported":False,
        })
    return output

def summarize_workitems(items,stage_ids):
    if not isinstance(items,list) or len(items)>MAX_IMPORT_STAGES:
        raise WindowsImportError("Invalid Windows work item collection")
    output=[]
    for item in items:
        if not isinstance(item,dict):
            raise WindowsImportError("Invalid Windows work item")
        stage_id=guid(item.get("StageId"),"work item stage")
        status=item.get("Status")
        agent=item.get("Agent")
        if status not in STATUSES or agent not in AGENTS:
            raise WindowsImportError("Unknown Windows work item status or agent")
        depends=item.get("DependsOn",[]) or []
        if not isinstance(depends,list) or len(depends)>MAX_IMPORT_STAGES:
            raise WindowsImportError("Unbounded Windows work item dependencies")
        output.append({
            "id":optional_guid(item.get("Id"),"work item"),
            "stageId":stage_id,
            "sourceStatus":status,
            "sourceAgent":agent,
            "dependsOn":[guid(x,"work item dependency") for x in depends],
            "sourceStagePresent":stage_id in stage_ids,
            "linuxState":"unmapped", "executable":False,
        })
    return output

def summarize_execution_records(records):
    """Retain bounded event identity/type/attribution, hash metadata, never logs."""
    output=[]
    for record in records:
        if not isinstance(record,dict):
            raise WindowsImportError("Invalid Windows execution record")
        kind=record.get("Kind")
        if not isinstance(kind,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{0,69}",kind):
            raise WindowsImportError("Invalid Windows execution event type")
        metadata=record.get("Metadata","")
        if not isinstance(metadata,str):
            raise WindowsImportError("Windows execution metadata must be text")
        evidence=record.get("Evidence","unknown")
        if evidence not in ("observed","imported","inferred","unknown"):
            raise WindowsImportError("Unsupported Windows execution evidence label")
        source=record.get("Source","")
        if not isinstance(source,str) or len(source)>128:
            raise WindowsImportError("Invalid Windows execution source")
        output.append({
            "id":optional_guid(record.get("Id"),"execution record"),
            "stageId":optional_guid(record.get("StageId"),"execution stage"),
            "runId":optional_guid(record.get("RunId"),"execution run"),
            "kind":kind, "evidence":evidence,
            "sourceKind":"aiws.local" if source=="aiws.local" else "other",
            "at":date_label(record.get("At"),"execution event"),
            "metadataSha256":hashlib.sha256(metadata.encode("utf-8")).hexdigest() if metadata else None,
            "payloadImported":False,
        })
    return output

def summarize_unified(unified):
    if unified is None:
        unified={}
    if not isinstance(unified,dict) or unified.get("SchemaVersion",1)!=1:
        raise WindowsImportError("Unsupported Windows UnifiedTaskState schema")
    plans=unified.get("Plans",[]) or []
    artifacts=unified.get("Artifacts",[]) or []
    runs=unified.get("AgentRuns",[]) or []
    if not isinstance(plans,list) or len(plans)>80 or not isinstance(artifacts,list) or len(artifacts)>500 or not isinstance(runs,list) or len(runs)>500:
        raise WindowsImportError("Unbounded Windows evidence collection")
    hashes=[]
    for item in plans:
        if not isinstance(item,dict):
            raise WindowsImportError("Invalid Windows plan revision")
        value=item.get("Sha256")
        if not isinstance(value,str) or not HEX.fullmatch(value):
            raise WindowsImportError("Windows plan revision is missing SHA256")
        hashes.append(value.lower())
    refs=[]
    for item in artifacts:
        if not isinstance(item,dict) or item.get("Kind") not in ("plan","stage-result"):
            raise WindowsImportError("Invalid Windows artifact")
        value=item.get("ContentHash")
        if not isinstance(value,str) or not HEX.fullmatch(value):
            raise WindowsImportError("Windows artifact hash missing")
        refs.append({"kind":item["Kind"],"sha256":value.lower()})
    run_summaries=[]
    for item in runs:
        if not isinstance(item,dict):
            raise WindowsImportError("Invalid Windows AgentRunRecord")
        agent=item.get("Agent")
        status=item.get("Status")
        if agent not in AGENTS or status not in STATUSES:
            raise WindowsImportError("Unrecognized Windows AgentRunRecord enum")
        adapter=item.get("AdapterId","")
        if not isinstance(adapter,str) or len(adapter)>128:
            raise WindowsImportError("Invalid Windows Agent adapter")
        evidence=item.get("Evidence","local-intent")
        if evidence not in ("local-intent","observed","imported","inferred","unknown"):
            raise WindowsImportError("Invalid Windows Agent evidence")
        run_summaries.append({
            "id":guid(item.get("Id"),"agent run"),
            "agent":agent,"status":status,
            "stageId":guid(item.get("StageId"),"run stage"),
            "adapterIdSha256":hashlib.sha256(adapter.encode("utf-8")).hexdigest() if adapter else None,
            "evidence":evidence,
            "startedAt":date_label(item.get("StartedAt"),"Agent start"),
            "completedAt":date_label(item.get("CompletedAt"),"Agent completion"),
            "linuxState":"history-only", "executable":False,
        })
    return {"planRevisionSha256":hashes,"artifactRefs":refs,"agentRuns":run_summaries}

def convert_windows_task(data):
    if not isinstance(data,dict):
        raise WindowsImportError("Windows WorkTask object expected")
    task_id=guid(data.get("Id"),"task")
    title=text(data.get("Title"),"title",160)
    graph=data.get("GraphMode",False)
    if not isinstance(graph,bool):
        raise WindowsImportError("Windows GraphMode must be boolean")
    steps=data.get("Steps")
    if not isinstance(steps,list) or not (1<=len(steps)<=MAX_IMPORT_STAGES):
        raise WindowsImportError("Windows import supports 1-32 workflow stages")
    unified=data.get("Unified") or {}
    metadata=summarize_unified(unified)
    goal=text(unified.get("Goal") or title,"goal",4000)
    executions=data.get("ExecutionRecords",[]) or []
    if not isinstance(executions,list) or len(executions)>2000:
        raise WindowsImportError("Invalid bounded Windows execution ledger")
    metadata["originalExecutionRecordCount"]=len(executions)
    metadata["graphMode"]=graph
    converted=[]
    ids=set()
    for i,entry in enumerate(steps):
        if not isinstance(entry,dict):
            raise WindowsImportError("Windows WorkflowStep object expected")
        stage_id=guid(entry.get("Id"),"step")
        if stage_id in ids:
            raise WindowsImportError("Duplicate Windows step ID")
        ids.add(stage_id)
        label=text(entry.get("Title"),"step title",160)
        status=entry.get("Status","Pending")
        agent=entry.get("Agent","Manual")
        if status not in STATUSES or agent not in AGENTS:
            raise WindowsImportError("Unknown Windows Agent or StepStatus")
        requires=entry.get("RequiresApproval",True)
        granted=entry.get("ApprovalGranted",False)
        if not isinstance(requires,bool) or not isinstance(granted,bool):
            raise WindowsImportError("Windows approval flags must be boolean")
        dep=entry.get("DependsOn",[]) or []
        if not isinstance(dep,list) or len(dep)>MAX_IMPORT_STAGES:
            raise WindowsImportError("Invalid Windows dependencies")
        dep=[guid(x,"dependency") for x in dep]
        if not graph:
            # Windows non-graph workflow is sequential, even when DependsOn=[].
            dep=[] if i==0 else [converted[-1]["key"]]
        result=entry.get("Result","")
        instructions=entry.get("Instructions","")
        if not isinstance(result,str) or not isinstance(instructions,str):
            raise WindowsImportError("Windows result/instructions must be strings")
        converted.append({
            "key":stage_id,"label":label,"dependsOn":dep,
            "windowsStatus":status,"windowsAgent":agent,
            "windowsRequiresApproval":requires,
            "windowsApprovalGranted":granted,
            "resultSha256":hashlib.sha256(result.encode("utf-8")).hexdigest() if result else None,
            "instructionsSha256":hashlib.sha256(instructions.encode("utf-8")).hexdigest() if instructions else None,
        })
    graph_map={x["key"]:x["dependsOn"] for x in converted}
    visited=set()
    def visit(key,active):
        if key in active:
            raise WindowsImportError("Windows DAG cycle")
        if key in visited:
            return
        for predecessor in graph_map[key]:
            if predecessor not in graph_map or predecessor==key:
                raise WindowsImportError("Unknown or self-referential Windows dependency")
            visit(predecessor,active|{key})
        visited.add(key)
    for key in graph_map:
        visit(key,set())
    metadata["stages"]=[{
        **{k:s[k] for k in ("key","windowsStatus","windowsAgent",
                        "windowsRequiresApproval","windowsApprovalGranted",
                        "resultSha256","instructionsSha256")},
        "linuxState":"unmapped", "executable":False,
    } for s in converted]
    metadata["planRevisions"]=summarize_plans(unified.get("Plans",[]) or [])
    metadata["workItems"]=summarize_workitems(unified.get("WorkItems",[]) or [],ids)
    metadata["executionRecords"]=summarize_execution_records(executions)
    metadata["workflowStages"]=[{
        "stageId":s["key"],"sourceStatus":s["windowsStatus"],
        "sourceAgent":s["windowsAgent"],"dependsOn":s["dependsOn"],
        "linuxState":"unmapped","executable":False,
    } for s in converted]
    metadata["sourceSha256"]=digest(data)
    return {"taskId":task_id,"title":title,"goal":goal,"stages":converted,
            "metadata":metadata}
