import React, {useEffect, useState} from "react";
import {SimplePopover, spinner} from "../utils";
import _ from "lodash";
import {Accordion, Alert, Button, Card, Form, Table} from "react-bootstrap";
import ReactMarkdown from "react-markdown";
import ReactStars from "react-stars";
import SetupHabitica from "./SetupHabitica";
import FieldModal from "./FieldModal";
import ChartModal from "./ChartModal";

import { useSelector, useDispatch } from 'react-redux'
import { fetch_, getFields } from '../redux/actions'

export default function Fields() {
  const [fetchingSvc, setFetchingSvc] = useState(false)
  const [fieldEntries, setFieldEntries] = useState({})
  const [showForm, setShowForm] = useState(false)
  const [showChart, setShowChart] = useState(false)

  const dispatch = useDispatch()
  const as = useSelector(state => state.as)
  const user = useSelector(state => state.user)
  const fields = useSelector(state => state.fields)

  const fetchFieldEntries = async () => {
    if (_.isEmpty(fields)) {return}
    const {data} = await dispatch(fetch_(`field-entries`, 'GET'))
    return setFieldEntries(data)
    // 3e896062: something about field_entries default_values?
  }

  useEffect(() => {
    fetchFieldEntries()
  }, [fields])

  if (_.get(fields, 'code') === 401) {
    return <h5>{fields.message}</h5>
  }

  const fetchService = async (service) => {
    setFetchingSvc(true)
    await dispatch(fetch_(`${service}/sync`, 'POST'))
    await dispatch(getFields())
    setFetchingSvc(false)
  }

  const changeFieldVal = (fid, direct=false) => e => {
    let v = direct ? e : e.target.value
    v = parseFloat(v)  // until we support strings
    setFieldEntries({...fieldEntries, [fid]: v})
    const body = {value: v}
    dispatch(fetch_(`field-entries/${fid}`, 'POST', body))
  }

  const changeCheck = fid => e => {
    changeFieldVal(fid, true)(~~!fieldEntries[fid])
  }

  const renderSyncButton = (service) => {
    if (!~['habitica'].indexOf(service)) {return null}
    if (as) {return null}
    if (!user.habitica_user_id) {return null}
    if (fetchingSvc) {return spinner}
    return <>
      <SimplePopover text='Gnothi auto-syncs every hour'>
        <Button onClick={() => fetchService(service)}>Sync</Button>
      </SimplePopover>
    </>
  }

  const onFormClose = () => {
    setShowForm(false)
    dispatch(getFields())
  }

  const onChartClose = () => {
    setShowChart(false)
  }

  const renderField = (f) => {
    return (
      <tr
        key={f.id}
        style={!f.excluded_at ? {} : {
          textDecoration: 'line-through',
          opacity: .5
        }}
      >
        <td
          onClick={() => setShowForm(f.id)}
          className='cursor-pointer'
        >
          <ReactMarkdown source={f.name} linkTarget='_blank' />
        </td>
        <td>
          {f.type === 'fivestar' ? (
            <ReactStars
              value={fieldEntries[f.id]}
              half={false}
              size={25}
              onChange={changeFieldVal(f.id, true)}
            />
          ) : f.type === 'check' ? (
            <>
              <Form.Check
                type='radio'
                label='Yes'
                id={f.id + '-yes'}
                inline
                checked={fieldEntries[f.id] > 0}
                onChange={changeCheck(f.id)}
              />
              <Form.Check
                type='radio'
                label='No'
                id={f.id + '-no'}
                inline
                checked={fieldEntries[f.id] < 1}
                onChange={changeCheck(f.id)}
              />
            </>
          ) : (
            <Form.Control
              disabled={!!f.service}
              type='number'
              size="sm"
              value={fieldEntries[f.id]}
              onChange={changeFieldVal(f.id)}
            />
          )}
        </td>
        <td>
          ~{f.avg && f.avg.toFixed(1)}
          <a
            onClick={() => setShowChart(f.id)}
            className='cursor-pointer'
          >📈</a>
        </td>
      </tr>
    )
  }

  // see 3b92a768 for dynamic field groups. Revisit when more than one service,
  // currently just habitica
  const groups = [{
    service: 'custom',
    name: 'Fields',
    fields: _(fields)
      .filter(v => !v.service && !v.excluded_at)
      .sortBy('id').value(),
    emptyText: () => <small className='text-muted'>
      <p>Fields are activity & quality trackers. Mood, sleep, substance, habits, etc. They can be numbers, checkboxes, or fivestar-ratings.<ul>
        <li>Track your mood, sleep patterns, substance intake, etc</li>
        <li>See stats (average, graphs, predictions)</li>
        <li>See how fields interact: correlation. Eg, "sleep most influenced by alcohol".</li>
        <li>Help long-term decisions by tracking options (fivestar-rate different jobs or moving destinations).</li>
        <li>Share fields, eg with a therapist who's interested in your mood or substances.</li>
        <li>For habits specifically, I recommend Habitica (below).</li>
      </ul></p>
    </small>
  }, {
    service: 'habitica',
    name: 'Habitica',
    fields: _(fields)
      .filter(v => v.service === 'habitica' && !v.excluded_at)
      .sortBy('id')
      .value(),
    emptyText: () => <small className='text-muted'>
      <p>For habit-tracking (exercise, substance, productivity, etc) I recommend <a href='https://habitica.com/' target='_blank'>Habitica</a>. Gnothi will sync Habitica habits & dailies.</p>
      <p>Use Gnothi fields for qualitative data (mood, sleep-quality, decisions) and Habitica for habits. Habitica doesn't support arbitrary number entries.</p>
      <p>Your UserID and API Token are database-encrypted. <em>All</em> sensitive data in Gnothi is encrypted.</p>
    </small>
  }, {
    service: 'excluded',
    name: 'Excluded',
    fields: _(fields)
      .filter(v => v.excluded_at)
      .sortBy('id')
      .value(),
    emptyText: () => <small className='text-muted'>
      <p>If you stop tracking a field, but keep it around just in case, click "Remove" and it will show up here.</p>
    </small>
  }]

  const renderButtons = g => {
    if (g.service === 'custom') {
      return <>
        {!as && <Button
          variant="success"
          size="sm"
          onClick={() => setShowForm(true)}
          className='bottom-margin'
        >New Field</Button>}
        {!!g.fields.length && <Button
          variant="outline-primary"
          style={{float:'right'}}
          size="sm"
          onClick={() => setShowChart(true)}
        >Top Influencers</Button>}
      </>
    }
    if (g.service === 'habitica' && !as) {
      return <SetupHabitica />
    }
    return null
  }

  const renderGroup = g => (
    <Card key={g.service}>
      <Accordion.Toggle as={Card.Header} variant="link" eventKey={g.service}>
        {g.name}
      </Accordion.Toggle>
      <Accordion.Collapse eventKey={g.service}>
        <Card.Body>
          <Table size='sm' borderless>
            <tbody>
            {g.fields.length ? g.fields.map(renderField) : g.emptyText()}
            </tbody>
            {renderSyncButton(g.service)}
          </Table>
          {renderButtons(g)}
        </Card.Body>
      </Accordion.Collapse>
    </Card>
  )

  return <div>
    {showForm && (
      <FieldModal
        close={onFormClose}
        field={showForm === true ? {} : fields[showForm]}
      />
    )}

    {showChart && (
      <ChartModal
        field={showChart === true ? null : fields[showChart]}
        overall={showChart === true}
        close={onChartClose}
      />
    )}

    <Accordion defaultActiveKey="custom">
      {groups.map(renderGroup)}
    </Accordion>
  </div>
}
