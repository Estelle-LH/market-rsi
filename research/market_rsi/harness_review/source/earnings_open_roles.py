# Source excerpt. Imports and other methods are omitted.

class _OpenRole:
    def _run_open(self, prompt, slot, instructions, response_format, decode, artifact, status):
        self._context()
        frozen = deepcopy(prompt)
        ctx, output = self.context, Path(slot)
        if (str(output) not in ctx['slots'] or not output.is_absolute() or output.resolve() != output):
            raise ValueError('Open role outside exact declared slot')
        limits = ctx['limits']
        cutoff = getattr(self.budget,'monotonic_deadline',ctx['cutoff_monotonic'])
        if type(cutoff) not in (int,float) or not math.isfinite(cutoff) or cutoff < 0:
            raise ValueError('Finite original budget cutoff required')
        hard = min(ctx['cutoff_monotonic'],cutoff,time.monotonic()+limits['wall_seconds'])
        if time.time() >= utc_epoch(ctx['cutoff_utc']) or time.monotonic() >= hard:
            raise BudgetStop('Open-role cutoff before factory')
        if output.exists() or output.is_symlink():
            raise FileExistsError('Consumed open-role slot remains closed to retry')
        self.budget.active()
        output.mkdir(parents=True,exist_ok=False)
        identity = (output.stat().st_dev,output.stat().st_ino)
        protected = {}
        def capture():
            for path in output.iterdir():
                if path.resolve() != path or not path.is_file():
                    raise ValueError('Nonregular open-role artifact')
                token = e.digest(path.read_bytes())
                if path in protected and protected[path] != token:
                    raise ValueError('Preserved open-role artifact changed during send')
                protected[path] = token
        def timely(*, check_budget=True):
            self._context()
            if (output.resolve() != output or (output.stat().st_dev,output.stat().st_ino) != identity
                    or self.broker.definitions != self.definitions):
                raise ValueError('Open-role output or broker drift')
            for path, token in protected.items():
                if path.resolve() != path or not path.is_file() or e.digest(path.read_bytes()) != token:
                    raise ValueError('Preserved open-role artifact drift')
            if time.time() >= utc_epoch(ctx['cutoff_utc']) or time.monotonic() >= hard:
                raise BudgetStop('Open-role original deadline reached')
            if check_budget:
                self.budget.active()
        initial_content, initial_policy = _initial_user_json(frozen, self.role)
        e.durable_json(output/'identity.json',{'context':self.binding,'source_commit':ctx['source_commit'],
            'evidence_scope':'source-bound open research transport; not empirical improvement',
            'model_authorship_verified':False,'max_turns':self.max_turns,'max_tool_calls':self.max_tool_calls,
            **({'initial_user_serialization': initial_policy} if initial_policy else {})})
        e.durable_json(output/'effective-input.json',frozen)
        capture()
        history = [{'role':'user','content':initial_content}]
        review_handoff = (self.role == 'review'
            and response_format.get('name') == 'earnings_population_review_v1')
        failure, chosen, last_response = None, None, None
        seen, tool_calls, turn = set(), 0, 0
        started = time.monotonic()
        try:
            timely()
            # The original owner verifies the exact in-flight reservation on
            # generation sends. active() here would reject our own reservation.
            client=self.factory()
            if self.socket_timeout_seconds is not None:
                client.timeout=self.socket_timeout_seconds
            transport = _CapacityDeadlineHTTP(client,lambda:timely(check_budget=False),deadline_utc=ctx['cutoff_utc'],
                rollout_seconds=limits['wall_seconds'],captured_deadline=hard)
            with e.absolute_window(hard-time.monotonic()):
                for turn in range(1,self.max_turns+1):
                    timely()
                    final = turn == self.max_turns
                    request = {'model':ctx['rates']['api_model'],'reasoning':{'effort':ctx['rates']['effort']},
                        'input':deepcopy(history),'instructions':instructions+(FINALIZE+
                            self._final_instruction() if final else ''),
                        'tools':deepcopy(self.definitions),
                        'tool_choice':'none' if final else 'auto','parallel_tool_calls':False,
                        'text':{'format':deepcopy(response_format)}}
                    completion=({**request,'tool_choice':'none',
                        'instructions':instructions+FINALIZE+self._final_instruction()}
                        if (self.role=='author' or review_handoff) and not final else None)
                    packed=pack(e.ReceiptHTTP(transport,output),request,limits,output,turn,
                        author_final=self.role=='author' and final,completion_request=completion,
                        review_final=review_handoff and final,
                        prepared_count_context=self.binding)
                    request,prepared_count=packed if type(packed) is tuple else (packed,None)
                    final=final or request['tool_choice']=='none'
                    capture(); timely()
                    budgeted_response(e.ReceiptHTTP(transport,output),request,ctx['rates'],limits,self.budget,output,turn,
                        **({} if prepared_count is None else {'prepared_count':prepared_count}))
                    last_response = output/f'{turn:02d}-response.json'
                    original = e.strict_json(last_response.read_text())
                    capture(); timely()
                    items = original.get('output')
                    if (type(items) is not list or any(type(item) is not dict
                            or item.get('type') not in {'reasoning','message','function_call'} for item in items)):
                        raise ValueError('Unsupported open-role response item')
                    calls = [item for item in items if item['type']=='function_call']
                    if not calls:
                        chosen = decode(original)
                        break
                    if final:
                        raise ValueError('Final open-role turn attempted tools')
                    if tool_calls+len(calls) > self.max_tool_calls:
                        raise ValueError('Open-role tool budget exhausted')
                    ids = [call.get('call_id') for call in calls]
                    if (any(type(token) is not str or not 1<=len(token)<=200 or token in seen for token in ids)
                            or len(set(ids)) != len(ids)):
                        raise ValueError('Missing or duplicate function-call identity')
                    seen.update(ids); history.extend(deepcopy(items))
                    for call in calls:
                        timely(); tool_calls += 1
                        try:
                            if (type(call.get('arguments')) is not str or len(call['arguments'].encode())>65536
                                    or type(call.get('name')) is not str):
                                raise ValueError('Bounded named tool arguments required')
                            args = e.strict_json(call['arguments'])
                            if type(args) is not dict:
                                raise ValueError('Exact object tool arguments required')
                            spec = next((item for item in self.definitions if item['name']==call['name']),None)
                            if spec is None:
                                raise ValueError('Unregistered broker tool')
                            arguments(args,spec['parameters'])
                            result = self.broker.dispatch(call['name'],args)
                            rendered = json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False)
                            if len(rendered.encode()) > 131072:
                                raise ValueError('Open-role tool observation exceeds bound')
                        except (ValueError,TypeError,KeyError,ArithmeticError,SyntaxError) as error:
                            rendered = json.dumps({'error':'Tool request rejected; original failure retained by broker when dispatched.',
                                                   'error_type':type(error).__name__},sort_keys=True)
                        timely()
                        observed = {'type':'function_call_output','call_id':call['call_id'],'output':rendered}
                        e.durable_json(output/f"{turn:02d}-tool-{raw_digest(call['call_id'].encode())[:12]}.json",observed)
                        history.append(observed); capture()
                if chosen is None:
                    raise RuntimeError('Open-role ended without a final business object')
            timely()
        except BaseException as error:
            failure = error
        finally:
            try:
                captured = sorted(output.glob('[0-9][0-9]-response.json'))
                if captured:
                    last_response = captured[-1]
                    save_bytes(output/'response.json',last_response.read_bytes())
                e.durable_json(output/'budget-summary.json',self.budget.summary())
            except BaseException as error:
                failure = failure or error
        if failure is None:
            try:
                timely()
                bound = {'path':str(output/'response.json'),'sha256':e.digest((output/'response.json').read_bytes())}
                e.durable_json(output/(artifact+'.json'),{artifact:chosen,'original':bound})
            except BaseException as error:
                failure = error
        e.durable_json(output/'result.json',{'status':status if failure is None else 'FAILED_NO_RETRY',
            'error_type':None if failure is None else type(failure).__name__,'turns':turn,'tool_calls':tool_calls,
            'wall_seconds':time.monotonic()-started,'retry_allowed':False,
            'final_numbered_response':None if last_response is None else last_response.name,
            'evidence_scope':'Actual counted role/tool originals require independent audit','model_authorship_verified':False})
        if failure is not None:
            if not isinstance(failure,Exception):
                raise failure
            raise RuntimeError('Open research role failed once; diagnose originals before a fresh attempt: '+type(failure).__name__) from failure
        return bound
