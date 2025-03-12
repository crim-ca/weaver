<!---
Utilities for rendering elements in other pages.
-->


<%def name="get_provider_link(provider_id, query='')">\
${weaver.wps_restapi_url}/providers/${provider_id}${f"?{query}" if query else ""}\
</%def>


<%def name="get_processes_link(provider_id='', query='')">\
<%
    _prefix = get_provider_link(provider_id) if provider_id else weaver.wps_restapi_url
%>
${_prefix}/processes${f"?{query}" if query else ""}\
</%def>


<%def name="get_process_link(process_id, provider_id='', query='')">\
${get_processes_link(provider_id=provider_id)}/${process_id}${f"?{query}" if query else ""}\
</%def>


<!--always apply 'detail' query to populate the table in one request-->
<%def name="get_jobs_link(query='')">\
${weaver.wps_restapi_url}/jobs${f"?{query}&detail=true" if query else "?detail=true"}\
</%def>


<%def name="get_job_link(job_id, query='')">\
${weaver.wps_restapi_url}/jobs/${job_id}${f"?{query}" if query else ""}\
</%def>


<!--
Assume that the definitions will be inserted into a 'nav-menu' with a parent HTML list block.
-->
<%def name="get_paging_links()">
    <%
        next_page = None
        prev_page = None
        last_page = None
        first_page = None
        for link in body.get("links") or []:
            if link.rel == "prev":
                prev_page = link.href
            if link.rel == "next":
                next_page = link.href
            if link.rel == "last":
                last_page = link.href
            if link.rel == "first":
                first_page = link.href
    %>
    %if first_page:
        <li>
            <div class="nav-link">
                Go to <a href="${first_page}">first page</a>.
            </div>
        </li>
    %endif
    %if prev_page:
        <li>
            <div class="nav-link">
                Go to <a href="${prev_page}">previous page</a>.
            </div>
        </li>
    %endif
    %if next_page:
        <li>
            <div class="nav-link">
                Go to <a href="${next_page}">next page</a>.
            </div>
        </li>
    %endif
    %if last_page:
        <li>
            <div class="nav-link">
                Go to <a href="${last_page}">last page</a>.
            </div>
        </li>
    %endif
</%def>


<!--
WARNING: newlines matter between 'pre', they will add extra whitespace. Leave them on the same line.
NOTE: class 'language-json' used by the 'ajax/libs/highlight.js' library inserted in the head scripts.
-->
<%def name="render_json(json_data, indent=2, **kwargs)">
    <pre><code class="language-json">${json.dumps(json_data, indent=indent, **kwargs)}</code></pre>
</%def>
<%def name="render_yaml(yaml_data, indent=2, **kwargs)">
    <pre><code class="language-yaml">${yaml.safe_dumps(yaml_data, indent=indent, **kwargs)}</code></pre>
</%def>


<%def name="render_bool(value)">
    <div class="code ${str(value).lower()}">
        ${str(value).lower()}
    </div>
</%def>


<%def name="render_status(status)">
    <div class="label status-unknown status-${status}">${status}</div>
</%def>


<%def name="render_progress(job_progress, job_status)">
    <progress
        value="${job_progress * 10}"
        max="1000"
        class="progress-${job_status}"
    >${job_progress}%</progress> ${job_progress}%
</%def>


<%def name="render_metadata(metadata)">
<dl class="indent">
%for meta in metadata:
    <dt>
        <div class="field-key">
        %if "title" in meta:
            Title: ${meta.title}
        %elif "role" in meta:
            Role: ${meta.role}
        %else:
            Rel: ${meta.rel}
        %endif
        </div>
    </dt>
    <dd>
        %if "href" in meta:
            <div class="code">
                <a href="${meta.href}">${meta.href}</a>
            </div>
        %else:
            <div class="code">${meta.value}</div>
        %endif
        %if "lang" in meta:
            <div class="field">
                <div class="field-key">Language:</div>
                <div class="language">${meta.lang}</div>
            </div>
        %elif "hreflang" in meta:
            <div class="field">
                <div class="field-key">Language:</div>
                <div class="language">${meta.hreflang}</div>
            </div>
        %endif
        %if "role" in meta:
            <div class="field">
                <div class="field-key">Role:</div>
                <div class="code">${meta.role}</div>
            </div>
        %endif
        %if "type" in meta:
            <div class="field indent">
                <div class="field-key">Media-Type:</div>
                <div class="code">${meta.type}</div>
            </div>
        %endif
    </dd>
%endfor
</dl>
</%def>


<%def name="render_links(links)">
<dl class="indent">
%for link in links:
    <dt>
        <div class="label code">${link.rel}</div>
    </dt>
    <dd>
        %if "title" in link:
            <div class="field-title">${link.title}</div>
        %endif
        <div class="code">
            <a href="${link.href}">${link.href}</a>
        </div>
        %if "hreflang" in link:
            <div class="field">
                <div class="field-key">Language:</div>
                <div class="language">${link.hreflang}</div>
            </div>
        %endif
        %if "type" in link:
            <div class="field">
                <div class="field-key">Media-Type:</div>
                <div class="code">${link.type}</div>
            </div>
        %endif
    </dd>
%endfor
</dl>
</%def>


<%def name="render_inputs(inputs)">
<dl class="indent">
%for input_id, input_data in inputs.items():
    <div class="process-input">
        <dt id="input-${input_id}">
            <div class="field-id inline code">
                <a href="#input-${input_id}">${input_id}</a>
            </div>
            %if "title" in input_data:
                <span class="dash">&#8212;</span>
                <span class="field-title">${input_data.title}</span>
            %endif
        </dt>
        <dd>
            %for field in ["description"]:
                %if field in input_data:
                <div class="field">
                    <div class="field-key field-sub">${field.capitalize()}:</div>
                    <div class="field-${field}">${input_data[field]}</div>
                </div>
                %endif
            %endfor
            <div class="field-key field-sub">Schema:</div>
            <div class="indent">
                <div class="inline">
                    <div class="field-key code">minOccurs = ${input_data.minOccurs}</div>
                    <div class="field-key">,</div>
                    <div class="field-key code">maxOccurs = ${input_data.maxOccurs}</div>
                </div>
                ${render_json(input_data.schema)}
            </div>
            <div class>
                <%
                    known_fields = {"title", "description", "schema", "minOccurs", "maxOccurs"}
                    extra_fields = set(input_data) - known_fields
                %>
                %if extra_fields:
                    <div class="field-key field-sub">Additional Details:</div>
                    <div class="indent">
                        %for field in extra_fields:
                            <div class="field-key field-extra">${field}:</div>
                            <div class="">${render_json(input_data[field])}</div>
                        %endfor
                    </div>
                %endif
            </div>
        </dd>
    </div>
%endfor
</dl>
</%def>


<%def name="render_outputs(outputs)">
<dl class="indent">
%for output_id, output_data in outputs.items():
    <div class="process-output">
        <dt id="output-${output_id}">
            <a href="#output-${output_id}">${output_id}</a>
        </dt>
        <dd>
            <div>
                <div class="field-key">Schema:</div>
                ${render_json(output_data.schema)}
            </div>
        </dd>
    </div>
%endfor
</dl>
</%def>


<!--
    Defines a dynamic 'toggle' button that will show/hide a code block, using the response content of a job sub-path.
    The code block and button display visibility and text are dynamically controlled and populated by state functions.
    Once fetched, the job 'type' response contents are cached into to the code block element to avoid fetching again.
    Classes are dynamically attributed with the corresponding 'type' parameter to allow different styling as needed.
    Note that the 'type' should be unique to avoid duplicate referencing of distinct button operations.
-->
<%def name="build_job_toggle_button_code(job, type, path, format, language, queries = '', name = '')">
<div>
    <script>
        async function fetch_job_${type}(format, queries) {
            const url = "${get_job_link(job.id)}";
            const qs = queries ? "&" + queries : "";
            const resp = await fetch(url + "${path}?f=" + format + qs);
            let data = "";
            if ("${language}" == "json") {
                data = await resp.json();
                data = JSON.stringify(data, null, 4);
            }
            else {
                data = await resp.text();
            }
            let code = hljs.highlight(data, {language: "${language}"}).value;
            let code_block = document.getElementById("job-${type}-content");
            toggle_job_${type}(true);
            code_block.innerHTML = code;
            let btn_show = document.getElementById("job-${type}-button-show");
            btn_show.onclick = toggle_job_${type};
        }
        function toggle_job_${type}(show) {
            let code_block = document.getElementById("job-${type}-content");
            let btn_show = document.getElementById("job-${type}-button-show");
            let btn_hide = document.getElementById("job-${type}-button-hide");
            code_block.parentElement.style.display = show ? "unset" : "none";
            btn_hide.style.display = show ? "unset" : "none";
            btn_show.style.display = show ? "none" : "unset";
        }
    </script>
    <button type="button" id="job-${type}-button-show"
            onclick="fetch_job_${type}('${format}', '${queries}')"
    >
        Display ${name or type.capitalize()}
    </button>
    <button
        type="button"
        id="job-${type}-button-hide"
        onclick="toggle_job_${type}(false)"
        style="display: none"
    >
        Hide ${name or type.capitalize()}
    </button>
    <pre style="display: none"><code id="job-${type}-content" class="language-${language}">></code></pre>
</div>
</%def>
