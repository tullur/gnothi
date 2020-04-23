import {Route, Switch, useRouteMatch, Redirect} from "react-router-dom"
import React from "react"
import Profile from "./Profile"
import Sharing from "./Sharing"

export default function ProfileRoutes({fetch_, as}) {
  let match = useRouteMatch()

  return (
    <Switch>
      <Route path={`${match.url}/profile`}>
        <Profile fetch_={fetch_} />
      </Route>
      <Route path={`${match.url}/sharing`}>
        <Sharing fetch_={fetch_} as={as} />
      </Route>
    </Switch>
  )
}