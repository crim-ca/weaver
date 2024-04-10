<%def name="get_processes_link(query="")">
    ${weaver.wps_restapi_url}/processes${f"?{query}" if query else ""}
</%def>

<%def name="get_process_link(process, query="")">
    ${weaver.wps_restapi_url}/processes/${process.id}${f"?{query}" if query else ""}
</%def>
